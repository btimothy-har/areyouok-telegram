"""Tests for Messages model."""

import hashlib
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram

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

    def test_to_telegram_object_with_payload(self):
        """Test converting database record to Telegram object."""
        msg = Messages()
        msg.message_type = "Message"
        msg.payload = {"message_id": 123, "text": "test"}

        # Mock the de_json method
        with patch.object(telegram.Message, "de_json") as mock_de_json:
            mock_de_json.return_value = MagicMock(spec=telegram.Message)
            result = msg.to_telegram_object()

            mock_de_json.assert_called_once_with(msg.payload, None)
            assert result == mock_de_json.return_value

    def test_to_telegram_object_soft_deleted(self):
        """Test soft deleted message returns None."""
        msg = Messages()
        msg.message_type = "Message"
        msg.payload = None

        assert msg.to_telegram_object() is None

    @pytest.mark.asyncio
    async def test_delete_soft_deletes_message(self, mock_db_session):
        """Test soft deleting a message."""
        msg = Messages()
        msg.payload = {"message_id": 123}

        result = await msg.delete(mock_db_session)

        assert result is True
        assert msg.payload is None
        mock_db_session.add.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_delete_already_deleted(self, mock_db_session):
        """Test deleting an already soft-deleted message."""
        msg = Messages()
        msg.payload = None

        result = await msg.delete(mock_db_session)

        assert result is False
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_or_update_message(self, mock_db_session, mock_telegram_message):
        """Test inserting a new message."""
        mock_result = AsyncMock()
        mock_db_session.execute.return_value = mock_result

        await Messages.new_or_update(
            mock_db_session,
            str(mock_telegram_message.from_user.id),
            str(mock_telegram_message.chat.id),
            mock_telegram_message,
        )

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify the statement is for messages table
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "table")
        assert call_args.table.name == "messages"
