"""Tests for handlers/messages.py."""

from datetime import UTC
from datetime import datetime
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
    async def test_on_new_message_with_existing_session(self, mock_db_session, frozen_time):
        """Test handling new message with existing active session."""
        # Create mock update with message
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message = MagicMock(spec=telegram.Message)
        mock_update.message.date = frozen_time
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_user.id = 456
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock active session
        mock_active_session = MagicMock()
        mock_active_session.new_message = AsyncMock()
        mock_active_session.session_key = "session_key_123"

        with (
            patch("areyouok_telegram.handlers.messages.Messages.new_or_update", new=AsyncMock()) as mock_msg_save,
            patch(
                "areyouok_telegram.handlers.messages.extract_media_from_telegram_message", new=AsyncMock()
            ) as mock_extract_media,
            patch(
                "areyouok_telegram.handlers.messages.Sessions.get_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ) as mock_get_session,
            patch(
                "areyouok_telegram.handlers.messages.Sessions.create_session", new=AsyncMock()
            ) as mock_create_session,
        ):
            await on_new_message(mock_update, mock_context)

            # Verify message was saved with session key
            mock_msg_save.assert_called_once_with(
                db_conn=mock_db_session,
                user_id=456,
                chat_id=789,
                message=mock_update.message,
                session_key="session_key_123",
            )

            # Verify media extraction was called
            mock_extract_media.assert_called_once_with(mock_db_session, mock_update.message)

            # Verify session lookup
            mock_get_session.assert_called_once_with(mock_db_session, "789")

            # Verify existing session was used
            mock_active_session.new_message.assert_called_once_with(
                db_conn=mock_db_session, timestamp=frozen_time, is_user=True
            )

            # Verify new session was not created
            mock_create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_new_message_without_existing_session(self, mock_db_session, frozen_time):
        """Test handling new message without existing active session."""
        # Create mock update with message
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message = MagicMock(spec=telegram.Message)
        mock_update.message.date = frozen_time
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_user.id = 456
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock new session
        mock_new_session = MagicMock()
        mock_new_session.new_message = AsyncMock()
        mock_new_session.session_key = "new_session_key"

        with (
            patch("areyouok_telegram.handlers.messages.Messages.new_or_update", new=AsyncMock()) as mock_msg_save,
            patch("areyouok_telegram.handlers.messages.extract_media_from_telegram_message", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.messages.Sessions.get_active_session", new=AsyncMock(return_value=None)
            ) as mock_get_session,
            patch(
                "areyouok_telegram.handlers.messages.Sessions.create_session",
                new=AsyncMock(return_value=mock_new_session),
            ) as mock_create_session,
        ):
            await on_new_message(mock_update, mock_context)

            # Verify session lookup
            mock_get_session.assert_called_once_with(mock_db_session, "789")

            # Verify new session was created
            mock_create_session.assert_called_once_with(mock_db_session, "789", frozen_time)

            # Verify message was saved with new session key
            mock_msg_save.assert_called_once_with(
                db_conn=mock_db_session,
                user_id=456,
                chat_id=789,
                message=mock_update.message,
                session_key="new_session_key",
            )

            # Verify message was recorded in new session
            mock_new_session.new_message.assert_called_once_with(
                db_conn=mock_db_session, timestamp=frozen_time, is_user=True
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
    async def test_on_edit_message_with_active_session_after_start(self, mock_db_session, frozen_time):
        """Test handling edited message with active session where original message is after session start."""
        # Create mock update with edited message
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.edited_message = MagicMock(spec=telegram.Message)
        mock_update.edited_message.date = frozen_time
        mock_update.edited_message.edit_date = datetime(2024, 1, 1, 12, 0, 1, tzinfo=UTC)
        mock_update.edited_message.message_id = 999
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_user.id = 456
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock active session
        mock_active_session = MagicMock()
        mock_active_session.session_start = datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC)
        mock_active_session.new_activity = AsyncMock()
        mock_active_session.session_key = "session_key_edit"

        with (
            patch("areyouok_telegram.handlers.messages.Messages.new_or_update", new=AsyncMock()) as mock_msg_save,
            patch(
                "areyouok_telegram.handlers.messages.extract_media_from_telegram_message", new=AsyncMock()
            ) as mock_extract_media,
            patch(
                "areyouok_telegram.handlers.messages.Sessions.get_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ),
        ):
            await on_edit_message(mock_update, mock_context)

            # Verify message was saved with session key
            mock_msg_save.assert_called_once_with(
                mock_db_session,
                user_id=456,
                chat_id=789,
                message=mock_update.edited_message,
                session_key="session_key_edit",
            )

            # Verify media extraction was called
            mock_extract_media.assert_called_once_with(mock_db_session, mock_update.edited_message)

            # Verify activity was recorded
            mock_active_session.new_activity.assert_called_once_with(
                db_conn=mock_db_session,
                timestamp=datetime(2024, 1, 1, 12, 0, 1, tzinfo=UTC),
                is_user=True,
            )

    @pytest.mark.asyncio
    async def test_on_edit_message_with_active_session_before_start(self, mock_db_session):
        """Test handling edited message where original message is before session start."""
        # Create mock update with edited message
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.edited_message = MagicMock(spec=telegram.Message)
        mock_update.edited_message.date = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)  # Before session start
        mock_update.edited_message.edit_date = datetime(2024, 1, 1, 12, 0, 1, tzinfo=UTC)
        mock_update.edited_message.message_id = 999
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_user.id = 456
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock active session
        mock_active_session = MagicMock()
        mock_active_session.session_start = datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC)
        mock_active_session.new_activity = AsyncMock()
        mock_active_session.session_key = "session_key_before"

        with (
            patch("areyouok_telegram.handlers.messages.Messages.new_or_update", new=AsyncMock()) as mock_msg_save,
            patch("areyouok_telegram.handlers.messages.extract_media_from_telegram_message", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.messages.Sessions.get_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ),
        ):
            await on_edit_message(mock_update, mock_context)

            # Verify message was saved without session key (not part of session)
            mock_msg_save.assert_called_once_with(
                mock_db_session,
                user_id=456,
                chat_id=789,
                message=mock_update.edited_message,
                session_key=None,
            )

            # Activity should not be recorded
            mock_active_session.new_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_edit_message_without_active_session(self, mock_db_session):
        """Test handling edited message without active session."""
        # Create mock update with edited message
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.edited_message = MagicMock(spec=telegram.Message)
        mock_update.edited_message.date = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_user.id = 456
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch("areyouok_telegram.handlers.messages.Messages.new_or_update", new=AsyncMock()) as mock_msg_save,
            patch(
                "areyouok_telegram.handlers.messages.extract_media_from_telegram_message", new=AsyncMock()
            ) as mock_extract_media,
            patch("areyouok_telegram.handlers.messages.Sessions.get_active_session", new=AsyncMock(return_value=None)),
        ):
            await on_edit_message(mock_update, mock_context)

            # Verify message was saved without session key
            mock_msg_save.assert_called_once_with(
                mock_db_session,
                user_id=456,
                chat_id=789,
                message=mock_update.edited_message,
                session_key=None,
            )

            # Media extraction should be called even without session
            mock_extract_media.assert_called_once_with(mock_db_session, mock_update.edited_message)

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
    async def test_on_message_react_with_active_session_after_start(self, mock_db_session, frozen_time):
        """Test handling message reaction with active session where reaction is after session start."""
        # Create mock update with message reaction
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_update.message_reaction.date = frozen_time
        mock_update.message_reaction.message_id = 999
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_user.id = 456
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock active session
        mock_active_session = MagicMock()
        mock_active_session.session_start = datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC)
        mock_active_session.new_activity = AsyncMock()
        mock_active_session.session_key = "session_key_react"

        with (
            patch("areyouok_telegram.handlers.messages.Messages.new_or_update", new=AsyncMock()) as mock_msg_save,
            patch(
                "areyouok_telegram.handlers.messages.Sessions.get_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ),
        ):
            await on_message_react(mock_update, mock_context)

            # Verify message/reaction was saved with session key
            mock_msg_save.assert_called_once_with(
                db_conn=mock_db_session,
                user_id=456,
                chat_id=789,
                message=mock_update.message_reaction,
                session_key="session_key_react",
            )

            # Verify activity was recorded
            mock_active_session.new_activity.assert_called_once_with(
                db_conn=mock_db_session,
                timestamp=frozen_time,
                is_user=True,
            )

    @pytest.mark.asyncio
    async def test_on_message_react_with_active_session_before_start(self, mock_db_session):
        """Test handling message reaction where reaction is before session start."""
        # Create mock update with message reaction
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_update.message_reaction.date = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)  # Before session start
        mock_update.message_reaction.message_id = 999
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_user.id = 456
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock active session
        mock_active_session = MagicMock()
        mock_active_session.session_start = datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC)
        mock_active_session.new_activity = AsyncMock()
        mock_active_session.session_key = "session_key_before_react"

        with (
            patch("areyouok_telegram.handlers.messages.Messages.new_or_update", new=AsyncMock()) as mock_msg_save,
            patch(
                "areyouok_telegram.handlers.messages.Sessions.get_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ),
        ):
            await on_message_react(mock_update, mock_context)

            # Verify message was saved without session key (not part of session)
            mock_msg_save.assert_called_once_with(
                db_conn=mock_db_session,
                user_id=456,
                chat_id=789,
                message=mock_update.message_reaction,
                session_key=None,
            )

            # Activity should not be recorded
            mock_active_session.new_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_react_without_active_session(self, mock_db_session):
        """Test handling message reaction without active session."""
        # Create mock update with message reaction
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_update.message_reaction.date = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_user.id = 456
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch("areyouok_telegram.handlers.messages.Messages.new_or_update", new=AsyncMock()) as mock_msg_save,
            patch("areyouok_telegram.handlers.messages.Sessions.get_active_session", new=AsyncMock(return_value=None)),
        ):
            await on_message_react(mock_update, mock_context)

            # Verify message was saved without session key
            mock_msg_save.assert_called_once_with(
                db_conn=mock_db_session,
                user_id=456,
                chat_id=789,
                message=mock_update.message_reaction,
                session_key=None,
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
