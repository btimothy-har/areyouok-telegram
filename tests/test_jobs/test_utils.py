"""Tests for jobs/utils.py."""

from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram

from areyouok_telegram.jobs.exceptions import UserNotFoundForChatError
from areyouok_telegram.jobs.utils import close_chat_session
from areyouok_telegram.jobs.utils import get_all_inactive_sessions
from areyouok_telegram.jobs.utils import get_chat_session
from areyouok_telegram.jobs.utils import get_user_encryption_key
from areyouok_telegram.jobs.utils import log_bot_activity
from areyouok_telegram.jobs.utils import save_session_context


class TestGetChatSession:
    """Test the get_chat_session function."""

    @pytest.mark.asyncio
    async def test_get_chat_session_success(self):
        """Test successfully retrieving active session."""
        mock_session = MagicMock()

        with patch("areyouok_telegram.jobs.utils.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch(
                "areyouok_telegram.jobs.utils.Sessions.get_active_session", new=AsyncMock(return_value=mock_session)
            ) as mock_get_active:
                result = await get_chat_session("chat123")

        assert result == mock_session
        # Verify Sessions.get_active_session was called with correct args
        mock_get_active.assert_called_once_with(mock_db_conn, "chat123")

    @pytest.mark.asyncio
    async def test_get_chat_session_no_active_session(self):
        """Test when no active session exists."""
        with patch("areyouok_telegram.jobs.utils.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch("areyouok_telegram.jobs.utils.Sessions.get_active_session", new=AsyncMock(return_value=None)):
                result = await get_chat_session("chat123")

        assert result is None


class TestGetAllInactiveSessions:
    """Test the get_all_inactive_sessions function."""

    @pytest.mark.asyncio
    async def test_get_all_inactive_sessions_success(self, frozen_time):
        """Test successfully retrieving inactive sessions."""
        mock_sessions = [MagicMock(), MagicMock()]
        from_dt = datetime(2024, 1, 1, tzinfo=UTC)
        to_dt = frozen_time

        with patch("areyouok_telegram.jobs.utils.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch(
                "areyouok_telegram.jobs.utils.Sessions.get_all_inactive_sessions",
                new=AsyncMock(return_value=mock_sessions),
            ) as mock_get_all:
                result = await get_all_inactive_sessions(from_dt, to_dt)

        assert result == mock_sessions
        # Verify Sessions.get_all_inactive_sessions was called with correct args
        mock_get_all.assert_called_once_with(mock_db_conn, from_dt, to_dt)

    @pytest.mark.asyncio
    async def test_get_all_inactive_sessions_empty(self):
        """Test when no inactive sessions exist."""
        from_dt = datetime(2024, 1, 1, tzinfo=UTC)
        to_dt = datetime(2024, 1, 2, tzinfo=UTC)

        with patch("areyouok_telegram.jobs.utils.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch(
                "areyouok_telegram.jobs.utils.Sessions.get_all_inactive_sessions", new=AsyncMock(return_value=[])
            ):
                result = await get_all_inactive_sessions(from_dt, to_dt)

        assert result == []


class TestGetUserEncryptionKey:
    """Test the get_user_encryption_key function."""

    @pytest.mark.asyncio
    async def test_get_user_encryption_key_success(self):
        """Test successfully retrieving user encryption key."""
        mock_user = MagicMock()
        mock_user.retrieve_key = MagicMock(return_value="test_encryption_key")
        mock_user.username = "testuser"

        with patch("areyouok_telegram.jobs.utils.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch(
                "areyouok_telegram.jobs.utils.Users.get_by_id", new=AsyncMock(return_value=mock_user)
            ) as mock_get_user:
                result = await get_user_encryption_key("chat123")

        assert result == "test_encryption_key"
        mock_get_user.assert_called_once_with(mock_db_conn, "chat123")
        mock_user.retrieve_key.assert_called_once_with()  # No username parameter

    @pytest.mark.asyncio
    async def test_get_user_encryption_key_user_not_found(self):
        """Test when user is not found (non-private chat)."""
        with patch("areyouok_telegram.jobs.utils.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch("areyouok_telegram.jobs.utils.Users.get_by_id", new=AsyncMock(return_value=None)):
                with pytest.raises(UserNotFoundForChatError) as exc_info:
                    await get_user_encryption_key("chat123")

        assert exc_info.value.chat_id == "chat123"
        assert "non-private chat" in str(exc_info.value)


class TestLogBotActivity:
    """Test the log_bot_activity function."""

    @pytest.mark.asyncio
    async def test_log_bot_activity_with_message(self, frozen_time):
        """Test logging bot activity with a response message."""
        mock_session = MagicMock()
        mock_session.session_id = "session_key_123"
        mock_session.new_activity = AsyncMock()
        mock_session.new_message = AsyncMock()

        # Create mock response message
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.date = frozen_time

        with patch("areyouok_telegram.jobs.utils.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch("areyouok_telegram.jobs.utils.Messages.new_or_update", new=AsyncMock()) as mock_new_or_update:
                await log_bot_activity(
                    bot_id="bot123",
                    user_encryption_key="test_encryption_key",
                    chat_id="chat456",
                    chat_session=mock_session,
                    response_message=mock_message,
                )

        # Verify new_activity was called with bot flag
        mock_session.new_activity.assert_called_once_with(db_conn=mock_db_conn, timestamp=frozen_time, is_user=False)

        # Verify message was saved
        mock_new_or_update.assert_called_once_with(
            mock_db_conn,
            "test_encryption_key",
            user_id="bot123",
            chat_id="chat456",
            message=mock_message,
            session_key="session_key_123",
        )

        # Verify new_message was called for telegram.Message
        mock_session.new_message.assert_called_once_with(db_conn=mock_db_conn, timestamp=frozen_time, is_user=False)

    @pytest.mark.asyncio
    async def test_log_bot_activity_with_reaction(self, frozen_time):
        """Test logging bot activity with a reaction message."""
        mock_session = MagicMock()
        mock_session.session_id = "session_key_123"
        mock_session.new_activity = AsyncMock()
        mock_session.new_message = AsyncMock()

        # Create mock reaction message
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)

        with patch("areyouok_telegram.jobs.utils.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch("areyouok_telegram.jobs.utils.Messages.new_or_update", new=AsyncMock()) as mock_new_or_update:
                await log_bot_activity(
                    bot_id="bot123",
                    user_encryption_key="test_encryption_key",
                    chat_id="chat456",
                    chat_session=mock_session,
                    response_message=mock_reaction,
                )

        # Verify new_activity was called
        mock_session.new_activity.assert_called_once_with(db_conn=mock_db_conn, timestamp=frozen_time, is_user=False)

        # Verify message was saved
        mock_new_or_update.assert_called_once_with(
            mock_db_conn,
            "test_encryption_key",
            user_id="bot123",
            chat_id="chat456",
            message=mock_reaction,
            session_key="session_key_123",
        )

        # Verify new_message was NOT called for MessageReactionUpdated
        mock_session.new_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_bot_activity_no_message(self, frozen_time):
        """Test logging bot activity without a response message."""
        mock_session = MagicMock()
        mock_session.session_id = "session_key_123"
        mock_session.new_activity = AsyncMock()
        mock_session.new_message = AsyncMock()

        with patch("areyouok_telegram.jobs.utils.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch("areyouok_telegram.jobs.utils.Messages.new_or_update", new=AsyncMock()) as mock_new_or_update:
                await log_bot_activity(
                    bot_id="bot123",
                    user_encryption_key="test_encryption_key",
                    chat_id="chat456",
                    chat_session=mock_session,
                    response_message=None,
                )

        # Verify new_activity was still called
        mock_session.new_activity.assert_called_once_with(db_conn=mock_db_conn, timestamp=frozen_time, is_user=False)

        # Verify message operations were not called
        mock_new_or_update.assert_not_called()
        mock_session.new_message.assert_not_called()


class TestSaveSessionContext:
    """Test the save_session_context function."""

    @pytest.mark.asyncio
    async def test_save_session_context_success(self):
        """Test successfully saving session context."""
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        # Create mock context template
        mock_context = MagicMock()
        mock_context.content = "Test context content"

        with patch("areyouok_telegram.jobs.utils.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch("areyouok_telegram.jobs.utils.Context.new_or_update", new=AsyncMock()) as mock_new_or_update:
                await save_session_context("test_encryption_key", "chat456", mock_session, mock_context)

        # Verify Context.new_or_update was called with correct args
        mock_new_or_update.assert_called_once_with(
            mock_db_conn,
            "test_encryption_key",
            chat_id="chat456",
            session_id="session123",
            ctype="session",
            content="Test context content",
        )


class TestCloseChatSession:
    """Test the close_chat_session function."""

    @pytest.mark.asyncio
    async def test_close_chat_session_success(self, frozen_time):
        """Test successfully closing a chat session."""
        mock_session = MagicMock()
        mock_session.close_session = AsyncMock()

        with patch("areyouok_telegram.jobs.utils.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            await close_chat_session(mock_session)

        # Verify close_session was called with current timestamp
        mock_session.close_session.assert_called_once_with(db_conn=mock_db_conn, timestamp=frozen_time)
