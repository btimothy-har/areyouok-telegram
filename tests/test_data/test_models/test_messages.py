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
from areyouok_telegram.encryption.exceptions import ContentNotDecryptedError


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the data cache before and after each test."""
    Messages._data_cache.clear()
    yield
    Messages._data_cache.clear()


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

        # Create message instance with encrypted payload and message_key
        msg = Messages()
        msg.message_key = "test_key"
        msg.encrypted_payload = encrypted

        # Decrypt should return JSON string
        decrypted = msg.decrypt_payload(user_key)
        assert decrypted == json.dumps(payload_dict)

        # Verify it's cached
        assert msg._data_cache["test_key"] == json.dumps(payload_dict)

    def test_decrypt_payload_no_encrypted_payload(self):
        """Test decrypt_payload returns None when no encrypted payload."""
        msg = Messages()
        msg.encrypted_payload = None
        user_key = Fernet.generate_key().decode("utf-8")

        result = msg.decrypt_payload(user_key)
        assert result is None

    def test_telegram_object_with_decrypted_payload(self):
        """Test accessing telegram_object property after decryption."""
        msg = Messages()
        msg.message_type = "Message"
        msg.message_key = "test_key"
        payload_dict = {"message_id": 123, "text": "test"}
        user_key = Fernet.generate_key().decode("utf-8")

        # Encrypt the payload
        msg.encrypted_payload = Messages.encrypt_payload(payload_dict, user_key)

        # First decrypt the payload to cache it
        msg.decrypt_payload(user_key)

        # Mock the de_json method
        with patch.object(telegram.Message, "de_json") as mock_de_json:
            mock_de_json.return_value = MagicMock(spec=telegram.Message)
            result = msg.telegram_object

            mock_de_json.assert_called_once_with(payload_dict, None)
            assert result == mock_de_json.return_value

    def test_telegram_object_not_decrypted(self):
        """Test accessing telegram_object before decryption raises error."""
        msg = Messages()
        msg.message_type = "Message"
        msg.message_key = "test_key"
        msg.encrypted_payload = "some_encrypted_data"
        # Don't cache anything - should raise ContentNotDecryptedError

        with pytest.raises(ContentNotDecryptedError):
            _ = msg.telegram_object

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
            user_encryption_key=user_key,
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

    @pytest.mark.asyncio
    async def test_new_or_update_message_with_reasoning(self, mock_db_session, mock_telegram_message):
        """Test inserting a message with reasoning."""
        mock_result = AsyncMock()
        mock_db_session.execute.return_value = mock_result
        user_key = Fernet.generate_key().decode("utf-8")

        # Mock to_dict to return a proper dictionary
        mock_telegram_message.to_dict.return_value = {"message_id": 123, "text": "test message", "chat": {"id": 456}}

        await Messages.new_or_update(
            mock_db_session,
            user_encryption_key=user_key,
            user_id=str(mock_telegram_message.from_user.id),
            chat_id=str(mock_telegram_message.chat.id),
            message=mock_telegram_message,
            reasoning="This is AI reasoning",
        )

        # Verify execute was called with reasoning
        mock_db_session.execute.assert_called_once()
        call_args = mock_db_session.execute.call_args[0][0]

        # Check that reasoning is included in the insert values
        assert "reasoning" in str(call_args)
