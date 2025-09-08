"""Tests for handlers/messages.py."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.handlers.exceptions import NoEditedMessageError
from areyouok_telegram.handlers.exceptions import NoMessageError
from areyouok_telegram.handlers.exceptions import NoMessageReactionError
from areyouok_telegram.handlers.messages import on_edit_message
from areyouok_telegram.handlers.messages import on_message_react
from areyouok_telegram.handlers.messages import on_new_message


class TestOnNewMessage:
    """Test the on_new_message handler."""

    @pytest.mark.asyncio
    async def test_on_new_message_handles_message_successfully(self, frozen_time, mock_telegram_user):
        """Test successful handling of new message."""
        # Create mock update with message
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message = MagicMock(spec=telegram.Message)
        mock_update.message.date = frozen_time
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Create mock active session
        mock_active_session = MagicMock()

        with (
            patch(
                "areyouok_telegram.handlers.messages.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ) as mock_get_session,
            patch(
                "areyouok_telegram.handlers.messages.data_operations.new_session_event", new=AsyncMock()
            ) as mock_new_event,
            patch("areyouok_telegram.handlers.messages.telegram_call", new=AsyncMock()) as mock_telegram_call,
        ):
            await on_new_message(mock_update, mock_context)

            # Verify session was retrieved/created
            mock_get_session.assert_called_once_with(
                chat_id=str(mock_update.effective_chat.id),
                timestamp=mock_update.message.date,
            )

            # Verify typing action was sent
            mock_telegram_call.assert_called_once_with(
                mock_context.bot.send_chat_action,
                chat_id=mock_update.effective_chat.id,
                action=telegram.constants.ChatAction.TYPING,
            )

            # Verify session event was recorded
            mock_new_event.assert_called_once_with(
                session=mock_active_session,
                message=mock_update.message,
                user_id=str(mock_telegram_user.id),
                is_user=True,
            )

    @pytest.mark.asyncio
    async def test_on_new_message_without_message_raises_error(self):
        """Test that handler raises NoMessageError when update has no message."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message = None

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with pytest.raises(NoMessageError) as exc_info:
            await on_new_message(mock_update, mock_context)

        assert exc_info.value.update_id == 123
        assert "Expected to receive a new message in update: 123" in str(exc_info.value)


class TestOnEditMessage:
    """Test the on_edit_message handler."""

    @pytest.mark.asyncio
    async def test_on_edit_message_handles_edited_message_successfully(self, mock_telegram_user):
        """Test successful handling of edited message."""
        # Create mock update with edited message
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.edited_message = MagicMock(spec=telegram.Message)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789
        mock_update.message = MagicMock(spec=telegram.Message)

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock active session
        mock_active_session = MagicMock()

        with (
            patch(
                "areyouok_telegram.handlers.messages.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ) as mock_get_session,
            patch(
                "areyouok_telegram.handlers.messages.data_operations.new_session_event", new=AsyncMock()
            ) as mock_new_event,
        ):
            await on_edit_message(mock_update, mock_context)

            # Verify session was retrieved/created
            mock_get_session.assert_called_once_with(
                chat_id=str(mock_update.effective_chat.id),
                timestamp=mock_update.message.date,
            )

            # Verify session event was recorded
            mock_new_event.assert_called_once_with(
                session=mock_active_session,
                message=mock_update.message,
                user_id=str(mock_telegram_user.id),
                is_user=True,
            )

    @pytest.mark.asyncio
    async def test_on_edit_message_without_edited_message_raises_error(self):
        """Test that handler raises NoEditedMessageError when update has no edited message."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.edited_message = None

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with pytest.raises(NoEditedMessageError) as exc_info:
            await on_edit_message(mock_update, mock_context)

        assert exc_info.value.update_id == 123
        assert "Expected to receive an edited message in update: 123" in str(exc_info.value)


class TestOnMessageReact:
    """Test the on_message_react handler."""

    @pytest.mark.asyncio
    async def test_on_message_react_handles_reaction_successfully(self, mock_telegram_user):
        """Test successful handling of message reaction."""
        # Create mock update with message reaction
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789
        mock_update.message = MagicMock(spec=telegram.Message)

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock active session
        mock_active_session = MagicMock()

        with (
            patch(
                "areyouok_telegram.handlers.messages.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ) as mock_get_session,
            patch(
                "areyouok_telegram.handlers.messages.data_operations.new_session_event", new=AsyncMock()
            ) as mock_new_event,
        ):
            await on_message_react(mock_update, mock_context)

            # Verify session was retrieved/created
            mock_get_session.assert_called_once_with(
                chat_id=str(mock_update.effective_chat.id),
                timestamp=mock_update.message.date,
            )

            # Verify session event was recorded
            mock_new_event.assert_called_once_with(
                session=mock_active_session,
                message=mock_update.message,
                user_id=str(mock_telegram_user.id),
                is_user=True,
            )

    @pytest.mark.asyncio
    async def test_on_message_react_without_reaction_raises_error(self):
        """Test that handler raises NoMessageReactionError when update has no message reaction."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message_reaction = None

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with pytest.raises(NoMessageReactionError) as exc_info:
            await on_message_react(mock_update, mock_context)

        assert exc_info.value.update_id == 123
        assert "Expected to receive a message reaction in update: 123" in str(exc_info.value)
