"""Tests for the setup.conversations module."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from telegram.ext import Application

from areyouok_telegram.setup.conversations import restore_active_sessions


class TestSetupConversationRunners:
    """Test the restore_active_sessions function."""

    @pytest.mark.asyncio
    async def test_setup_conversation_runners_with_active_sessions(self):
        """Test restore_active_sessions schedules jobs for active sessions."""
        # Arrange
        mock_context = MagicMock(spec=Application)

        # Mock active sessions
        mock_session1 = MagicMock()
        mock_session1.chat_id = "123456"
        mock_session2 = MagicMock()
        mock_session2.chat_id = "789012"
        active_sessions = [mock_session1, mock_session2]

        with (
            patch("areyouok_telegram.setup.conversations.async_database_session") as mock_db_session,
            patch("areyouok_telegram.setup.conversations.Sessions.get_all_active_sessions") as mock_get_sessions,
            patch("areyouok_telegram.setup.conversations.schedule_conversation_job") as mock_schedule_job,
        ):
            # Configure mocks
            mock_db_session.return_value.__aenter__.return_value = AsyncMock()
            mock_get_sessions.return_value = active_sessions
            mock_schedule_job.return_value = AsyncMock()  # Return an awaitable

            # Act
            await restore_active_sessions(mock_context)

            # Assert
            mock_get_sessions.assert_called_once_with(mock_db_session.return_value.__aenter__.return_value)

            # Verify schedule_conversation_job was called for each session
            assert mock_schedule_job.call_count == 2
            mock_schedule_job.assert_any_call(context=mock_context, chat_id="123456")
            mock_schedule_job.assert_any_call(context=mock_context, chat_id="789012")

    @pytest.mark.asyncio
    async def test_setup_conversation_runners_no_active_sessions(self):
        """Test restore_active_sessions handles no active sessions gracefully."""
        # Arrange
        mock_context = MagicMock(spec=Application)

        with (
            patch("areyouok_telegram.setup.conversations.async_database_session") as mock_db_session,
            patch("areyouok_telegram.setup.conversations.Sessions.get_all_active_sessions") as mock_get_sessions,
            patch("areyouok_telegram.setup.conversations.schedule_conversation_job") as mock_schedule_job,
            patch("logging.info") as mock_logging,
        ):
            # Configure mocks
            mock_db_session.return_value.__aenter__.return_value = AsyncMock()
            mock_get_sessions.return_value = []  # No active sessions

            # Act
            await restore_active_sessions(mock_context)

            # Assert
            mock_get_sessions.assert_called_once_with(mock_db_session.return_value.__aenter__.return_value)
            mock_logging.assert_called_once_with("No active sessions found, skipping conversation job setup.")
            mock_schedule_job.assert_not_called()
