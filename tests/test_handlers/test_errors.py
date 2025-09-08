"""Tests for handlers/errors.py."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from areyouok_telegram.handlers.errors import on_error_event


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
            patch("areyouok_telegram.handlers.errors.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.errors.DEVELOPER_CHAT_ID", "dev123"),
            patch("areyouok_telegram.handlers.errors.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.errors.logfire.info") as mock_log_info,
            patch("areyouok_telegram.handlers.errors.telegram_call", new=AsyncMock()) as mock_telegram_call,
        ):
            await on_error_event(mock_update, mock_context)

            # Verify error logging
            mock_log_exception.assert_called_once_with(str(mock_error), _exc_info=mock_error)

            # Verify update was saved
            mock_update_save.assert_called_once_with(mock_db_session, update=mock_update)

            # Verify developer notification via telegram_call
            mock_telegram_call.assert_called_once()
            call_args = mock_telegram_call.call_args
            assert call_args[0][0] == mock_context.bot.send_message  # First arg is the function
            assert call_args.kwargs["chat_id"] == "dev123"
            assert "An exception was raised while handling an update" in call_args.kwargs["text"]
            assert call_args.kwargs["parse_mode"] == ParseMode.MARKDOWN_V2

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
            patch("areyouok_telegram.handlers.errors.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.errors.DEVELOPER_CHAT_ID", "dev123"),
            patch("areyouok_telegram.handlers.errors.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.errors.logfire.info") as mock_log_info,
            patch("areyouok_telegram.handlers.errors.telegram_call", new=AsyncMock()) as mock_telegram_call,
        ):
            await on_error_event(None, mock_context)

            # Verify error logging
            mock_log_exception.assert_called_once_with(str(mock_error), _exc_info=mock_error)

            # Update should not be saved
            mock_update_save.assert_not_called()

            # Developer notification should still be sent
            mock_telegram_call.assert_called_once()
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
            patch("areyouok_telegram.handlers.errors.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.errors.DEVELOPER_CHAT_ID", None),
            patch("areyouok_telegram.handlers.errors.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.errors.logfire.info") as mock_log_info,
            patch("areyouok_telegram.handlers.errors.telegram_call", new=AsyncMock()) as mock_telegram_call,
        ):
            await on_error_event(mock_update, mock_context)

            # Verify error logging
            mock_log_exception.assert_called_once_with(str(mock_error), _exc_info=mock_error)

            # Verify update was saved
            mock_update_save.assert_called_once_with(mock_db_session, update=mock_update)

            # No developer notification should be sent
            mock_telegram_call.assert_not_called()
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
        mock_context.bot = AsyncMock()

        # Mock telegram_call to raise exception on first call, succeed on second
        send_exception = Exception("Failed to send message")
        mock_telegram_call_side_effect = [send_exception, None]

        with (
            patch("areyouok_telegram.handlers.errors.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.errors.DEVELOPER_CHAT_ID", "dev123"),
            patch("areyouok_telegram.handlers.errors.DEVELOPER_THREAD_ID", "thread456"),
            patch("areyouok_telegram.handlers.errors.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.errors.logfire.info") as mock_log_info,
            patch(
                "areyouok_telegram.handlers.errors.telegram_call",
                new=AsyncMock(side_effect=mock_telegram_call_side_effect),
            ) as mock_telegram_call,
        ):
            await on_error_event(mock_update, mock_context)

            # Verify error logging for original error
            assert mock_log_exception.call_count == 2
            mock_log_exception.assert_any_call(str(mock_error), _exc_info=mock_error)

            # Verify error logging for send message failure
            mock_log_exception.assert_any_call(
                "Failed to send error notification to developer",
                _exc_info=send_exception,
                chat_id="dev123",
                thread_id="thread456",
            )

            # Verify update was saved
            mock_update_save.assert_called_once_with(mock_db_session, update=mock_update)

            # Verify two telegram_call calls - first fails, second succeeds with fallback
            assert mock_telegram_call.call_count == 2

            # First call with formatted message (fails)
            first_call = mock_telegram_call.call_args_list[0]
            assert first_call.kwargs["chat_id"] == "dev123"
            assert first_call.kwargs["message_thread_id"] == "thread456"
            assert "An exception was raised while handling an update" in first_call.kwargs["text"]
            assert first_call.kwargs["parse_mode"] == ParseMode.MARKDOWN_V2

            # Second call with fallback message (succeeds)
            second_call = mock_telegram_call.call_args_list[1]
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
            patch("areyouok_telegram.handlers.errors.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.errors.DEVELOPER_CHAT_ID", "dev123"),
            patch("areyouok_telegram.handlers.errors.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.errors.logfire.info") as mock_log_info,
            patch("areyouok_telegram.handlers.errors.traceback.format_exception", return_value=[long_traceback]),
            patch(
                "areyouok_telegram.handlers.errors.split_long_message",
                return_value=["Part 1 content", "Part 2 content"],
            ) as mock_split,
            patch("areyouok_telegram.handlers.errors.telegram_call", new=AsyncMock()) as mock_telegram_call,
        ):
            await on_error_event(mock_update, mock_context)

            # Verify error logging
            mock_log_exception.assert_called_once_with(str(mock_error), _exc_info=mock_error)

            # Verify update was saved
            mock_update_save.assert_called_once_with(mock_db_session, update=mock_update)

            # Verify split_long_message was called
            mock_split.assert_called_once()

            # Verify two messages sent with part indicators
            assert mock_telegram_call.call_count == 2

            # First message should have "Part 1/2" header
            first_call = mock_telegram_call.call_args_list[0]
            assert "*Part 1/2*" in first_call.kwargs["text"]
            assert "Part 1 content" in first_call.kwargs["text"]

            # Second message should have "Part 2/2" header
            second_call = mock_telegram_call.call_args_list[1]
            assert "*Part 2/2*" in second_call.kwargs["text"]
            assert "Part 2 content" in second_call.kwargs["text"]

            # Verify info log with correct part count
            mock_log_info.assert_called_once_with("Error notification sent to developer (2 parts).")

    @pytest.mark.asyncio
    async def test_on_error_event_both_notifications_fail(self, mock_db_session):
        """Test error handler when both main and fallback notifications fail."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 789

        # Create mock context with error
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_error = Exception("Test error")
        mock_context.error = mock_error
        mock_context.bot = AsyncMock()

        # Mock telegram_call to fail on both calls
        main_exception = Exception("Main notification failed")
        fallback_exception = Exception("Fallback notification failed")
        mock_telegram_call_side_effect = [main_exception, fallback_exception]

        with (
            patch("areyouok_telegram.handlers.errors.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.errors.DEVELOPER_CHAT_ID", "dev123"),
            patch("areyouok_telegram.handlers.errors.DEVELOPER_THREAD_ID", "thread456"),
            patch("areyouok_telegram.handlers.errors.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.errors.logfire.info") as mock_log_info,
            patch(
                "areyouok_telegram.handlers.errors.telegram_call",
                new=AsyncMock(side_effect=mock_telegram_call_side_effect),
            ) as mock_telegram_call,
        ):
            # The error handler should complete successfully without raising
            await on_error_event(mock_update, mock_context)

            # Verify error logging for original error
            assert mock_log_exception.call_count == 3
            mock_log_exception.assert_any_call(str(mock_error), _exc_info=mock_error)

            # Verify error logging for main notification failure
            mock_log_exception.assert_any_call(
                "Failed to send error notification to developer",
                _exc_info=main_exception,
                chat_id="dev123",
                thread_id="thread456",
            )

            # Verify error logging for fallback notification failure
            mock_log_exception.assert_any_call(
                "Fallback error notification to developer failed.",
                _exc_info=fallback_exception,
                chat_id="dev123",
                thread_id="thread456",
            )

            # Verify update was saved
            mock_update_save.assert_called_once_with(mock_db_session, update=mock_update)

            # Verify both telegram_call calls were attempted
            assert mock_telegram_call.call_count == 2

            # First call with formatted message (fails)
            first_call = mock_telegram_call.call_args_list[0]
            assert first_call.kwargs["chat_id"] == "dev123"
            assert first_call.kwargs["message_thread_id"] == "thread456"
            assert "An exception was raised while handling an update" in first_call.kwargs["text"]
            assert first_call.kwargs["parse_mode"] == ParseMode.MARKDOWN_V2

            # Second call with fallback message (also fails)
            second_call = mock_telegram_call.call_args_list[1]
            assert second_call.kwargs["chat_id"] == "dev123"
            assert second_call.kwargs["message_thread_id"] == "thread456"
            assert (
                second_call.kwargs["text"]
                == "Error: Failed to send error notification to developer. Please check logs."
            )
            assert "parse_mode" not in second_call.kwargs

            # Verify info log is still called despite failures
            mock_log_info.assert_called_once_with("Error notification sent to developer (1 parts).")

    @pytest.mark.asyncio
    async def test_on_error_event_network_error_early_return(self, mock_db_session):
        """Test error handler returns early for NetworkError without notifications."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 789

        # Create mock context with NetworkError
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_error = telegram.error.NetworkError("Network connection failed")
        mock_context.error = mock_error
        mock_context.bot = AsyncMock()

        with (
            patch("areyouok_telegram.handlers.errors.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.errors.DEVELOPER_CHAT_ID", "dev123"),
            patch("areyouok_telegram.handlers.errors.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.errors.logfire.info") as mock_log_info,
            patch("areyouok_telegram.handlers.errors.telegram_call", new=AsyncMock()) as mock_telegram_call,
        ):
            await on_error_event(mock_update, mock_context)

            # Verify error logging still happens
            mock_log_exception.assert_called_once_with(str(mock_error), _exc_info=mock_error)

            # Verify update was saved
            mock_update_save.assert_called_once_with(mock_db_session, update=mock_update)

            # Verify NO developer notification was sent (early return)
            mock_telegram_call.assert_not_called()
            mock_log_info.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_error_event_timeout_error_early_return(self, mock_db_session):
        """Test error handler returns early for TimedOut error without notifications."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 789

        # Create mock context with TimedOut error
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_error = telegram.error.TimedOut("Request timed out")
        mock_context.error = mock_error
        mock_context.bot = AsyncMock()

        with (
            patch("areyouok_telegram.handlers.errors.Updates.new_or_upsert", new=AsyncMock()) as mock_update_save,
            patch("areyouok_telegram.handlers.errors.DEVELOPER_CHAT_ID", "dev123"),
            patch("areyouok_telegram.handlers.errors.logfire.exception") as mock_log_exception,
            patch("areyouok_telegram.handlers.errors.logfire.info") as mock_log_info,
            patch("areyouok_telegram.handlers.errors.telegram_call", new=AsyncMock()) as mock_telegram_call,
        ):
            await on_error_event(mock_update, mock_context)

            # Verify error logging still happens
            mock_log_exception.assert_called_once_with(str(mock_error), _exc_info=mock_error)

            # Verify update was saved
            mock_update_save.assert_called_once_with(mock_db_session, update=mock_update)

            # Verify NO developer notification was sent (early return)
            mock_telegram_call.assert_not_called()
            mock_log_info.assert_not_called()
