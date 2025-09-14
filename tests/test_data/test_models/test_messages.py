"""Tests for Messages model."""

import hashlib
import json
from datetime import UTC
from datetime import datetime
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
    """Clear the data and reasoning caches before and after each test."""
    Messages._data_cache.clear()
    Messages._reasoning_cache.clear()
    yield
    Messages._data_cache.clear()
    Messages._reasoning_cache.clear()


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

    def test_encrypt(self):
        """Test content encryption for both dict and string."""
        payload_dict = {"message_id": 123, "text": "test message"}
        reasoning_text = "AI reasoning"
        user_key = Fernet.generate_key().decode("utf-8")

        # Test dict encryption (payload)
        encrypted_payload = Messages.encrypt(payload_dict, user_key)

        # Test string encryption (reasoning)
        encrypted_reasoning = Messages.encrypt(reasoning_text, user_key)

        # Should be strings (base64 encoded encrypted data)
        assert isinstance(encrypted_payload, str)
        assert len(encrypted_payload) > 0
        assert isinstance(encrypted_reasoning, str)
        assert len(encrypted_reasoning) > 0

        # Should be able to decrypt them back
        fernet = Fernet(user_key.encode())

        # Decrypt payload
        decrypted_payload_bytes = fernet.decrypt(encrypted_payload.encode("utf-8"))
        decrypted_dict = json.loads(decrypted_payload_bytes.decode("utf-8"))
        assert decrypted_dict == payload_dict

        # Decrypt reasoning
        decrypted_reasoning_bytes = fernet.decrypt(encrypted_reasoning.encode("utf-8"))
        decrypted_reasoning = decrypted_reasoning_bytes.decode("utf-8")
        assert decrypted_reasoning == reasoning_text

    def test_decrypt(self):
        """Test payload and reasoning decryption."""
        payload_dict = {"message_id": 456, "text": "another test"}
        reasoning_text = "AI reasoning for this message"
        user_key = Fernet.generate_key().decode("utf-8")

        # First encrypt both
        encrypted_payload = Messages.encrypt(payload_dict, user_key)
        encrypted_reasoning = Messages.encrypt(reasoning_text, user_key)

        # Create message instance with encrypted content and message_key
        msg = Messages()
        msg.message_key = "test_key"
        msg.encrypted_payload = encrypted_payload
        msg.encrypted_reasoning = encrypted_reasoning

        # Decrypt should cache both
        msg.decrypt(user_key)

        # Verify payload is cached
        assert msg._data_cache["test_key"] == json.dumps(payload_dict)

        # Verify reasoning is cached
        assert msg._reasoning_cache["test_key"] == reasoning_text

    def test_decrypt_no_encrypted_content(self):
        """Test decrypt handles cases with no encrypted content."""
        msg = Messages()
        msg.message_key = "test_key"
        msg.encrypted_payload = None
        msg.encrypted_reasoning = None
        user_key = Fernet.generate_key().decode("utf-8")

        # Should not raise an error
        msg.decrypt(user_key)

        # Verify nothing is cached
        assert "test_key" not in msg._data_cache
        assert "test_key" not in msg._reasoning_cache

    def test_reasoning_property(self):
        """Test reasoning property access."""
        reasoning_text = "AI reasoning for this message"
        user_key = Fernet.generate_key().decode("utf-8")

        # Test with encrypted reasoning
        msg = Messages()
        msg.message_key = "test_key"
        msg.encrypted_reasoning = Messages.encrypt(reasoning_text, user_key)

        # Before decryption, should raise error
        with pytest.raises(ContentNotDecryptedError):
            _ = msg.reasoning

        # After decryption, should return reasoning
        msg.decrypt(user_key)
        assert msg.reasoning == reasoning_text

        # Test with no encrypted reasoning
        msg2 = Messages()
        msg2.message_key = "test_key_2"
        msg2.encrypted_reasoning = None
        msg2.decrypt(user_key)
        assert msg2.reasoning is None

    def test_telegram_object_with_decrypted_payload(self):
        """Test accessing telegram_object property after decryption."""
        msg = Messages()
        msg.message_type = "Message"
        msg.message_key = "test_key"
        payload_dict = {"message_id": 123, "text": "test"}
        user_key = Fernet.generate_key().decode("utf-8")

        # Encrypt the payload
        msg.encrypted_payload = Messages.encrypt(payload_dict, user_key)

        # First decrypt the payload to cache it
        msg.decrypt(user_key)

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

    @pytest.mark.asyncio
    async def test_new_or_update_invalid_message_type(self, mock_db_session):
        """Test new_or_update with invalid message type raises error."""
        user_key = Fernet.generate_key().decode("utf-8")

        # Create a mock object that is NOT a MessageTypes
        invalid_message = MagicMock()
        invalid_message.__class__.__name__ = "InvalidMessage"

        with pytest.raises(InvalidMessageTypeError) as exc_info:
            await Messages.new_or_update(
                mock_db_session,
                user_encryption_key=user_key,
                user_id="123",
                chat_id="456",
                message=invalid_message,
            )

        assert exc_info.value.message_type == "InvalidMessage"

    @pytest.mark.asyncio
    async def test_retrieve_message_by_id_found_with_reactions(self, mock_db_session):
        """Test retrieving a message by ID with reactions."""
        # Mock the message result
        mock_message = MagicMock(spec=Messages)
        mock_message.message_id = "123"
        mock_message.chat_id = "456"

        # Mock the first query result (main message)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_message

        # Mock the reaction messages
        mock_reaction1 = MagicMock(spec=Messages)
        mock_reaction2 = MagicMock(spec=Messages)

        # Mock the second query result (reactions)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_reaction1, mock_reaction2]
        mock_reaction_result = MagicMock()
        mock_reaction_result.scalars.return_value = mock_scalars

        # Set up the database session to return different results for different queries
        mock_db_session.execute.side_effect = [mock_result, mock_reaction_result]

        message, reactions = await Messages.retrieve_message_by_id(
            mock_db_session,
            message_id="123",
            chat_id="456",
            include_reactions=True,
        )

        assert message == mock_message
        assert reactions == [mock_reaction1, mock_reaction2]
        assert mock_db_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_retrieve_message_by_id_found_without_reactions(self, mock_db_session):
        """Test retrieving a message by ID without reactions."""
        # Mock the message result
        mock_message = MagicMock(spec=Messages)
        mock_message.message_id = "123"
        mock_message.chat_id = "456"

        # Mock the first query result (main message)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_message

        mock_db_session.execute.return_value = mock_result

        message, reactions = await Messages.retrieve_message_by_id(
            mock_db_session,
            message_id="123",
            chat_id="456",
            include_reactions=False,
        )

        assert message == mock_message
        assert reactions is None
        # Only one query should be executed (no reaction query)
        assert mock_db_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_retrieve_message_by_id_not_found(self, mock_db_session):
        """Test retrieving a message by ID when message not found."""
        # Mock the query result to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db_session.execute.return_value = mock_result

        message, reactions = await Messages.retrieve_message_by_id(
            mock_db_session,
            message_id="999",
            chat_id="456",
            include_reactions=True,
        )

        assert message is None
        # reactions should be empty list since no message was found
        assert reactions == []
        # Only one query should be executed (no reaction query since no message found)
        assert mock_db_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_retrieve_message_by_id_found_no_reactions(self, mock_db_session):
        """Test retrieving a message by ID when message exists but has no reactions."""
        # Mock the message result
        mock_message = MagicMock(spec=Messages)
        mock_message.message_id = "123"
        mock_message.chat_id = "456"

        # Mock the first query result (main message)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_message

        # Mock the second query result (empty reactions)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_reaction_result = MagicMock()
        mock_reaction_result.scalars.return_value = mock_scalars

        mock_db_session.execute.side_effect = [mock_result, mock_reaction_result]

        message, reactions = await Messages.retrieve_message_by_id(
            mock_db_session,
            message_id="123",
            chat_id="456",
            include_reactions=True,
        )

        assert message == mock_message
        assert reactions == []
        assert mock_db_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_retrieve_by_session(self, mock_db_session):
        """Test retrieving messages by session ID."""
        # Create mock message objects
        mock_message1 = MagicMock(spec=Messages)
        mock_message1.session_key = "session_123"
        mock_message1.created_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)

        mock_message2 = MagicMock(spec=Messages)
        mock_message2.session_key = "session_123"
        mock_message2.created_at = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)

        # Mock the query result
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_message1, mock_message2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db_session.execute.return_value = mock_result

        messages = await Messages.retrieve_by_session(
            mock_db_session,
            session_id="session_123",
        )

        assert len(messages) == 2
        assert messages == [mock_message1, mock_message2]
        mock_db_session.execute.assert_called_once()

        # Verify the query includes session_key filter and ordering
        call_args = mock_db_session.execute.call_args[0][0]
        query_str = str(call_args)
        assert "session_key" in query_str
        assert "ORDER BY" in query_str

    @pytest.mark.asyncio
    async def test_retrieve_by_session_empty_result(self, mock_db_session):
        """Test retrieving messages by session ID when no messages exist."""
        # Mock empty query result
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db_session.execute.return_value = mock_result

        messages = await Messages.retrieve_by_session(
            mock_db_session,
            session_id="nonexistent_session",
        )

        assert messages == []
        mock_db_session.execute.assert_called_once()
