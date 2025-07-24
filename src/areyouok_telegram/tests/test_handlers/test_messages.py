from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from areyouok_telegram.handlers import on_edit_message
from areyouok_telegram.handlers import on_new_message


class TestNewMessageHandler:
    """Test suite for message handlers functionality."""

    @pytest.mark.asyncio
    async def test_on_new_message(self, mock_async_database_session, mock_update_private_chat_new_message):
        """Test on_new_message with the expected payload for a new private message."""
        mock_context = AsyncMock()

        with patch("areyouok_telegram.data.Messages.new_or_update") as mock_messages_new_or_update:
            # Act
            await on_new_message(mock_update_private_chat_new_message, mock_context)

            mock_messages_new_or_update.assert_called_once_with(
                mock_async_database_session,
                user_id=mock_update_private_chat_new_message.effective_user.id,
                chat_id=mock_update_private_chat_new_message.effective_chat.id,
                message=mock_update_private_chat_new_message.message,
            )

    @pytest.mark.asyncio
    async def test_no_message_received(self, mock_async_database_session, mock_update_empty):
        """Test on_new_message raises NoMessageError when no message is received."""
        mock_context = AsyncMock()

        with pytest.raises(Exception) as exc_info:
            await on_new_message(mock_update_empty, mock_context)

        assert str(exc_info.value) == f"Expected to receive a new message in update: {mock_update_empty.update_id}"

        # Ensure no database operations were attempted
        mock_async_database_session.assert_not_called()


class TestEditMessageHandler:
    """Test suite for message edit handlers functionality."""

    @pytest.mark.asyncio
    async def test_on_edit_message(self, mock_async_database_session, mock_update_private_chat_edited_message):
        """Test on_edit_message with the expected payload for an edited private message."""
        mock_context = AsyncMock()

        with patch("areyouok_telegram.data.Messages.new_or_update") as mock_messages_new_or_update:
            # Act
            await on_edit_message(mock_update_private_chat_edited_message, mock_context)

            mock_messages_new_or_update.assert_called_once_with(
                mock_async_database_session,
                user_id=mock_update_private_chat_edited_message.effective_user.id,
                chat_id=mock_update_private_chat_edited_message.effective_chat.id,
                message=mock_update_private_chat_edited_message.edited_message,
            )

    @pytest.mark.asyncio
    async def test_no_message_received(self, mock_async_database_session, mock_update_empty):
        """Test on_edit_message with the expected payload for an edited private message."""
        mock_context = AsyncMock()

        with pytest.raises(Exception) as exc_info:
            await on_edit_message(mock_update_empty, mock_context)

        assert str(exc_info.value) == f"Expected to receive an edited message in update: {mock_update_empty.update_id}"

        # Ensure no database operations were attempted
        mock_async_database_session.assert_not_called()
