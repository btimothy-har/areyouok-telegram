"""Tests for handlers/globals.py."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.handlers.globals import on_error_event
from areyouok_telegram.handlers.globals import on_new_update


class TestOnNewUpdate:
    """Test the on_new_update handler."""

    @pytest.mark.asyncio
    async def test_on_new_update_with_user_and_chat(self, mock_db_session):
        """Test on_new_update processes user and chat correctly."""
        # Create mock update with user and chat
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_user.id = 123
        mock_update.effective_user.username = "testuser"
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 456

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock user object returned from new_or_update
        mock_user_obj = MagicMock()
        mock_user_obj.encrypted_key = "encrypted_key"
        mock_user_obj.retrieve_key = MagicMock(return_value="decrypted_key")

        with (
            patch(
                "areyouok_telegram.handlers.globals.Users.new_or_update", new=AsyncMock(return_value=mock_user_obj)
            ) as mock_user_update,
            patch("areyouok_telegram.handlers.globals.Chats.new_or_update", new=AsyncMock()) as mock_chat_update,
            patch("areyouok_telegram.handlers.globals.schedule_job", new=AsyncMock()) as mock_schedule_job,
            patch("areyouok_telegram.handlers.globals.ConversationJob") as mock_conversation_job,
            patch("areyouok_telegram.handlers.globals.logfire.span"),
        ):
            # Call the handler
            await on_new_update(mock_update, mock_context)

            # Verify database operations
            mock_user_update.assert_called_once_with(db_conn=mock_db_session, user=mock_update.effective_user)
            mock_chat_update.assert_called_once_with(db_conn=mock_db_session, chat=mock_update.effective_chat)

            # Verify key unlock was called
            mock_user_obj.retrieve_key.assert_called_once_with("testuser")

            # Verify job scheduling
            mock_conversation_job.assert_called_once_with(chat_id="456")
            mock_schedule_job.assert_called_once()
            call_args = mock_schedule_job.call_args
            assert call_args.kwargs["context"] == mock_context
            assert call_args.kwargs["job"] == mock_conversation_job.return_value
            assert call_args.kwargs["interval"] == timedelta(seconds=10)
            # Check that first is approximately 10 seconds in the future
            first_time = call_args.kwargs["first"]
            expected_time = datetime.now(UTC) + timedelta(seconds=10)
            assert abs((first_time - expected_time).total_seconds()) < 1

    @pytest.mark.asyncio
    async def test_on_new_update_without_user(self, mock_db_session):
        """Test on_new_update when update has no user."""
        # Create mock update without user
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = None
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 456

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch("areyouok_telegram.handlers.globals.Users.new_or_update", new=AsyncMock()) as mock_user_update,
            patch("areyouok_telegram.handlers.globals.Chats.new_or_update", new=AsyncMock()) as mock_chat_update,
            patch("areyouok_telegram.handlers.globals.schedule_job", new=AsyncMock()),
            patch("areyouok_telegram.handlers.globals.ConversationJob"),
            patch("areyouok_telegram.handlers.globals.logfire.span"),
        ):
            await on_new_update(mock_update, mock_context)

            # User update should not be called
            mock_user_update.assert_not_called()
            # Chat update should still be called
            mock_chat_update.assert_called_once_with(db_conn=mock_db_session, chat=mock_update.effective_chat)

    @pytest.mark.asyncio
    async def test_on_new_update_without_chat(self, mock_db_session):
        """Test on_new_update when update has no chat."""
        # Create mock update without chat
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_user.id = 123
        mock_update.effective_user.username = "testuser"
        mock_update.effective_chat = None

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock user object returned from new_or_update
        mock_user_obj = MagicMock()
        mock_user_obj.encrypted_key = "encrypted_key"
        mock_user_obj.retrieve_key = MagicMock(return_value="decrypted_key")

        with (
            patch(
                "areyouok_telegram.handlers.globals.Users.new_or_update", new=AsyncMock(return_value=mock_user_obj)
            ) as mock_user_update,
            patch("areyouok_telegram.handlers.globals.Chats.new_or_update", new=AsyncMock()) as mock_chat_update,
            patch("areyouok_telegram.handlers.globals.schedule_job", new=AsyncMock()) as mock_schedule_job,
            patch("areyouok_telegram.handlers.globals.ConversationJob") as mock_conversation_job,
            patch("areyouok_telegram.handlers.globals.logfire.span"),
        ):
            # This should raise an AttributeError when trying to access chat.id
            with pytest.raises(AttributeError):
                await on_new_update(mock_update, mock_context)

            # User update should be called
            mock_user_update.assert_called_once_with(db_conn=mock_db_session, user=mock_update.effective_user)
            # Key unlock should be called
            mock_user_obj.retrieve_key.assert_called_once_with("testuser")
            # Chat update should not be called
            mock_chat_update.assert_not_called()
            # Job should not be scheduled
            mock_schedule_job.assert_not_called()
            mock_conversation_job.assert_not_called()


class TestOnErrorEvent:
    """Test the on_error_event handler."""

    @pytest.mark.asyncio
    async def test_on_error_event_with_update_and_developer_chat(self, mock_db_session):
        """Test error handler with update and developer chat configured."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 789

        # Create mock context with error
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_error = Exception("Test error")
        mock_context.error = mock_error
        mock_context.bot = AsyncMock()

        with (
            patch("areyouok_telegram.handlers.globals.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.globals.DEVELOPER_CHAT_ID", "dev123"),
            patch("areyouok_telegram.handlers.globals.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.globals.logfire.info") as mock_log_info,
        ):
            await on_error_event(mock_update, mock_context)

            # Verify error logging
            mock_log_exception.assert_called_once_with("Test error", _exc_info=mock_error)

            # Verify update was saved
            mock_update_save.assert_called_once_with(mock_db_session, update=mock_update)

            # Verify developer notification
            mock_context.bot.send_message.assert_called_once()
            call_args = mock_context.bot.send_message.call_args
            assert call_args.kwargs["chat_id"] == "dev123"
            assert "An exception was raised while handling an update" in call_args.kwargs["text"]
            assert call_args.kwargs["parse_mode"] == telegram.constants.ParseMode.MARKDOWN_V2

            # Verify info log
            mock_log_info.assert_called_once_with("Error notification sent to developer.")

    @pytest.mark.asyncio
    async def test_on_error_event_without_update(self):
        """Test error handler when update is None."""
        # Create mock context with error
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_error = Exception("Test error")
        mock_context.error = mock_error
        mock_context.bot = AsyncMock()

        with (
            patch("areyouok_telegram.handlers.globals.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.globals.DEVELOPER_CHAT_ID", "dev123"),
            patch("areyouok_telegram.handlers.globals.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.globals.logfire.info") as mock_log_info,
        ):
            await on_error_event(None, mock_context)

            # Verify error logging
            mock_log_exception.assert_called_once_with("Test error", _exc_info=mock_error)

            # Update should not be saved
            mock_update_save.assert_not_called()

            # Developer notification should still be sent
            mock_context.bot.send_message.assert_called_once()
            mock_log_info.assert_called_once_with("Error notification sent to developer.")

    @pytest.mark.asyncio
    async def test_on_error_event_without_developer_chat(self, mock_db_session):
        """Test error handler when developer chat is not configured."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 789

        # Create mock context with error
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_error = Exception("Test error")
        mock_context.error = mock_error
        mock_context.bot = AsyncMock()

        with (
            patch("areyouok_telegram.handlers.globals.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.globals.DEVELOPER_CHAT_ID", None),
            patch("areyouok_telegram.handlers.globals.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.globals.logfire.info") as mock_log_info,
        ):
            await on_error_event(mock_update, mock_context)

            # Verify error logging
            mock_log_exception.assert_called_once_with("Test error", _exc_info=mock_error)

            # Verify update was saved
            mock_update_save.assert_called_once_with(mock_db_session, update=mock_update)

            # No developer notification should be sent
            mock_context.bot.send_message.assert_not_called()
            mock_log_info.assert_not_called()
