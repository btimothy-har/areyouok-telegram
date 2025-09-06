"""Tests for handlers/globals.py."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from telegram.constants import ChatType
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
        mock_update.effective_chat.type = ChatType.PRIVATE

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock user object returned from new_or_update
        mock_user_obj = MagicMock()

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
            mock_user_update.assert_called_once_with(mock_db_session, user=mock_update.effective_user)
            mock_chat_update.assert_called_once_with(mock_db_session, chat=mock_update.effective_chat)

            # Verify job scheduling
            mock_conversation_job.assert_called_once_with(chat_id="456")
            mock_schedule_job.assert_called_once()
            call_args = mock_schedule_job.call_args
            assert call_args.kwargs["context"] == mock_context
            assert call_args.kwargs["job"] == mock_conversation_job.return_value
            assert call_args.kwargs["interval"] == timedelta(seconds=3)
            # Check that first is approximately 2 seconds in the future
            first_time = call_args.kwargs["first"]
            expected_time = datetime.now(UTC) + timedelta(seconds=2)
            assert abs((first_time - expected_time).total_seconds()) < 1

    @pytest.mark.asyncio
    async def test_on_new_update_with_group_chat(self, mock_db_session):
        """Test on_new_update with group chat - job should not be scheduled."""
        # Create mock update with user and group chat
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_user.id = 123
        mock_update.effective_user.username = "testuser"
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 456
        mock_update.effective_chat.type = ChatType.GROUP

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock user object returned from new_or_update
        mock_user_obj = MagicMock()

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
            mock_user_update.assert_called_once_with(mock_db_session, user=mock_update.effective_user)
            mock_chat_update.assert_called_once_with(mock_db_session, chat=mock_update.effective_chat)

            # Verify job scheduling DID NOT happen for group chat
            mock_conversation_job.assert_not_called()
            mock_schedule_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_new_update_with_channel(self, mock_db_session):
        """Test on_new_update with channel - job should not be scheduled."""
        # Create mock update with user and channel
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_user.id = 123
        mock_update.effective_user.username = "testuser"
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 456
        mock_update.effective_chat.type = ChatType.CHANNEL

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock user object returned from new_or_update
        mock_user_obj = MagicMock()

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
            mock_user_update.assert_called_once_with(mock_db_session, user=mock_update.effective_user)
            mock_chat_update.assert_called_once_with(mock_db_session, chat=mock_update.effective_chat)

            # Verify job scheduling DID NOT happen for channel
            mock_conversation_job.assert_not_called()
            mock_schedule_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_new_update_without_user(self, mock_db_session):
        """Test on_new_update when update has no user."""
        # Create mock update without user
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = None
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 456
        mock_update.effective_chat.type = ChatType.PRIVATE

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
            mock_chat_update.assert_called_once_with(mock_db_session, chat=mock_update.effective_chat)

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

        with (
            patch(
                "areyouok_telegram.handlers.globals.Users.new_or_update", new=AsyncMock(return_value=mock_user_obj)
            ) as mock_user_update,
            patch("areyouok_telegram.handlers.globals.Chats.new_or_update", new=AsyncMock()) as mock_chat_update,
            patch("areyouok_telegram.handlers.globals.schedule_job", new=AsyncMock()) as mock_schedule_job,
            patch("areyouok_telegram.handlers.globals.ConversationJob") as mock_conversation_job,
            patch("areyouok_telegram.handlers.globals.logfire.span"),
        ):
            # Call the handler - it should complete successfully without chat
            await on_new_update(mock_update, mock_context)

            # User update should be called
            mock_user_update.assert_called_once_with(mock_db_session, user=mock_update.effective_user)
            # Chat update should not be called
            mock_chat_update.assert_not_called()
            # Job should not be scheduled since there's no chat
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
            mock_log_info.assert_called_once_with("Error notification sent to developer (1 parts).")

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
            mock_log_info.assert_called_once_with("Error notification sent to developer (1 parts).")

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

    @pytest.mark.asyncio
    async def test_on_error_event_send_message_fails(self, mock_db_session):
        """Test error handler when sending message to developer fails."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 789

        # Create mock context with error
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_error = Exception("Test error")
        mock_context.error = mock_error

        # Mock bot to raise exception on first call, succeed on second
        mock_bot = AsyncMock()
        send_exception = Exception("Failed to send message")
        mock_bot.send_message.side_effect = [send_exception, None]
        mock_context.bot = mock_bot

        with (
            patch("areyouok_telegram.handlers.globals.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.globals.DEVELOPER_CHAT_ID", "dev123"),
            patch("areyouok_telegram.handlers.globals.DEVELOPER_THREAD_ID", "thread456"),
            patch("areyouok_telegram.handlers.globals.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.globals.logfire.info") as mock_log_info,
        ):
            await on_error_event(mock_update, mock_context)

            # Verify error logging for original error
            assert mock_log_exception.call_count == 2
            mock_log_exception.assert_any_call("Test error", _exc_info=mock_error)

            # Verify error logging for send message failure
            mock_log_exception.assert_any_call(
                "Failed to send error notification to developer",
                _exc_info=send_exception,
                chat_id="dev123",
                thread_id="thread456",
            )

            # Verify update was saved
            mock_update_save.assert_called_once_with(mock_db_session, update=mock_update)

            # Verify two send_message calls - first fails, second succeeds with fallback
            assert mock_bot.send_message.call_count == 2

            # First call with formatted message (fails)
            first_call = mock_bot.send_message.call_args_list[0]
            assert first_call.kwargs["chat_id"] == "dev123"
            assert first_call.kwargs["message_thread_id"] == "thread456"
            assert "An exception was raised while handling an update" in first_call.kwargs["text"]
            assert first_call.kwargs["parse_mode"] == telegram.constants.ParseMode.MARKDOWN_V2

            # Second call with fallback message (succeeds)
            second_call = mock_bot.send_message.call_args_list[1]
            assert second_call.kwargs["chat_id"] == "dev123"
            assert second_call.kwargs["message_thread_id"] == "thread456"
            assert (
                second_call.kwargs["text"]
                == "Error: Failed to send error notification to developer. Please check logs."
            )
            assert "parse_mode" not in second_call.kwargs

            # Verify info log
            mock_log_info.assert_called_once_with("Error notification sent to developer (1 parts).")

    @pytest.mark.asyncio
    async def test_on_error_event_multipart_message(self, mock_db_session):
        """Test error handler with very long error message requiring multiple parts."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 789

        # Create mock context with error that has very long traceback
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_error = Exception("Test error")
        mock_context.error = mock_error
        mock_context.bot = AsyncMock()

        # Create a very long traceback that will trigger message splitting
        long_traceback = "\n".join([f"Line {i}: Very long line with lots of details" * 10 for i in range(200)])

        with (
            patch("areyouok_telegram.handlers.globals.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.globals.DEVELOPER_CHAT_ID", "dev123"),
            patch("areyouok_telegram.handlers.globals.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.globals.logfire.info") as mock_log_info,
            patch("areyouok_telegram.handlers.globals.traceback.format_exception", return_value=[long_traceback]),
            patch(
                "areyouok_telegram.handlers.globals.split_long_message",
                return_value=["Part 1 content", "Part 2 content"],
            ) as mock_split,
        ):
            await on_error_event(mock_update, mock_context)

            # Verify error logging
            mock_log_exception.assert_called_once_with("Test error", _exc_info=mock_error)

            # Verify update was saved
            mock_update_save.assert_called_once_with(mock_db_session, update=mock_update)

            # Verify split_long_message was called
            mock_split.assert_called_once()

            # Verify two messages sent with part indicators
            assert mock_context.bot.send_message.call_count == 2

            # First message should have "Part 1/2" header
            first_call = mock_context.bot.send_message.call_args_list[0]
            assert "*Part 1/2*" in first_call.kwargs["text"]
            assert "Part 1 content" in first_call.kwargs["text"]

            # Second message should have "Part 2/2" header
            second_call = mock_context.bot.send_message.call_args_list[1]
            assert "*Part 2/2*" in second_call.kwargs["text"]
            assert "Part 2 content" in second_call.kwargs["text"]

            # Verify info log with correct part count
            mock_log_info.assert_called_once_with("Error notification sent to developer (2 parts).")
