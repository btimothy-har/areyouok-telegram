"""Tests for handlers/globals.py."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram
from telegram.constants import ChatType
from telegram.ext import ContextTypes

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
            assert call_args.kwargs["interval"] == timedelta(milliseconds=500)
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
