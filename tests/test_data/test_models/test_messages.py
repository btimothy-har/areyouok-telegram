"""Tests for Messages model."""

import hashlib
import json
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from cryptography.fernet import Fernet

from areyouok_telegram.data.models.messages import InvalidMessageTypeError
from areyouok_telegram.data.models.messages import Messages


class TestMessages:
    """Test Messages model."""

    def test_generate_message_key(self):
        """Test message key generation."""
        user_id = "123"
        chat_id = "456"
        message_id = 789
        message_type = "Message"

        expected = hashlib.sha256(f"{user_id}:{chat_id}:{message_id}:{message_type}".encode()).hexdigest()
        assert Messages.generate_message_key(user_id, chat_id, message_id, message_type) == expected

    def test_message_type_obj_for_message(self):
        """Test getting Message type from message_type string."""
        msg = Messages()
        msg.message_type = "Message"
        assert msg.message_type_obj == telegram.Message

    def test_message_type_obj_for_reaction(self):
        """Test getting MessageReactionUpdated type from message_type string."""
        msg = Messages()
        msg.message_type = "MessageReactionUpdated"
        assert msg.message_type_obj == telegram.MessageReactionUpdated

    def test_message_type_obj_invalid_type(self):
        """Test invalid message type raises error."""
        msg = Messages()
        msg.message_type = "InvalidType"

        with pytest.raises(InvalidMessageTypeError) as exc_info:
            _ = msg.message_type_obj

        assert exc_info.value.message_type == "InvalidType"

    def test_encrypt_payload(self):
        """Test payload encryption."""
        payload_dict = {"message_id": 123, "text": "test message"}
        user_key = Fernet.generate_key().decode("utf-8")

        encrypted = Messages.encrypt_payload(payload_dict, user_key)

        # Should be a string (base64 encoded encrypted data)
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0

        # Should be able to decrypt it back
        fernet = Fernet(user_key.encode())
        decrypted_bytes = fernet.decrypt(encrypted.encode("utf-8"))
        decrypted_dict = json.loads(decrypted_bytes.decode("utf-8"))
        assert decrypted_dict == payload_dict

    def test_decrypt_payload(self):
        """Test payload decryption."""
        payload_dict = {"message_id": 456, "text": "another test"}
        user_key = Fernet.generate_key().decode("utf-8")

        # First encrypt
        encrypted = Messages.encrypt_payload(payload_dict, user_key)

        # Create message instance with encrypted payload
        msg = Messages()
        msg.encrypted_payload = encrypted

        # Decrypt should return original dict
        decrypted = msg.decrypt_payload(user_key)
        assert decrypted == payload_dict

    def test_decrypt_payload_no_encrypted_payload(self):
        """Test decrypt_payload returns None when no encrypted payload."""
        msg = Messages()
        msg.encrypted_payload = None
        user_key = Fernet.generate_key().decode("utf-8")

        result = msg.decrypt_payload(user_key)
        assert result is None

    def test_to_telegram_object_with_encrypted_payload(self):
        """Test converting database record to Telegram object with encrypted payload."""
        msg = Messages()
        msg.message_type = "Message"
        payload_dict = {"message_id": 123, "text": "test"}
        user_key = Fernet.generate_key().decode("utf-8")

        # Encrypt the payload
        msg.encrypted_payload = Messages.encrypt_payload(payload_dict, user_key)

        # Mock the de_json method
        with patch.object(telegram.Message, "de_json") as mock_de_json:
            mock_de_json.return_value = MagicMock(spec=telegram.Message)
            result = msg.to_telegram_object(user_key)

            mock_de_json.assert_called_once_with(payload_dict, None)
            assert result == mock_de_json.return_value

    def test_to_telegram_object_soft_deleted(self):
        """Test soft deleted message returns None."""
        msg = Messages()
        msg.message_type = "Message"
        msg.encrypted_payload = None
        user_key = Fernet.generate_key().decode("utf-8")

        assert msg.to_telegram_object(user_key) is None

    @pytest.mark.asyncio
    async def test_delete_soft_deletes_message(self, mock_db_session):
        """Test soft deleting a message."""
        msg = Messages()
        msg.encrypted_payload = "encrypted_data"

        result = await msg.delete(mock_db_session)

        assert result is True
        assert msg.encrypted_payload is None
        mock_db_session.add.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_delete_already_deleted(self, mock_db_session):
        """Test deleting an already soft-deleted message."""
        msg = Messages()
        msg.encrypted_payload = None

        result = await msg.delete(mock_db_session)

        assert result is False
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_or_update_message(self, mock_db_session, mock_telegram_message):
        """Test inserting a new message."""
        mock_result = AsyncMock()
        mock_db_session.execute.return_value = mock_result
        user_key = Fernet.generate_key().decode("utf-8")

        # Mock to_dict to return a proper dictionary
        mock_telegram_message.to_dict.return_value = {"message_id": 123, "text": "test message", "chat": {"id": 456}}

        await Messages.new_or_update(
            mock_db_session,
            user_key,
            user_id=str(mock_telegram_message.from_user.id),
            chat_id=str(mock_telegram_message.chat.id),
            message=mock_telegram_message,
        )

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify the statement is for messages table
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "table")
        assert call_args.table.name == "messages"
