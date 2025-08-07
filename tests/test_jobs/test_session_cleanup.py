"""Tests for jobs/session_cleanup.py."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from telegram.ext import ContextTypes

from areyouok_telegram.jobs.session_cleanup import SessionCleanupJob


class TestSessionCleanupJob:
    """Test the SessionCleanupJob class."""

    def test_init(self):
        """Test SessionCleanupJob initialization."""
        job = SessionCleanupJob()

        assert job.last_cleanup_timestamp is None
        assert job.name == "session_cleanup"

    def test_name_property(self):
        """Test name property returns correct value."""
        job = SessionCleanupJob()
        assert job.name == "session_cleanup"

    @pytest.mark.asyncio
    async def test_run_first_time_no_sessions(self, frozen_time):
        """Test first run with no inactive sessions."""
        job = SessionCleanupJob()
        job._run_timestamp = frozen_time

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch("areyouok_telegram.jobs.session_cleanup.get_all_inactive_sessions", new=AsyncMock(return_value=[])),
            patch("areyouok_telegram.jobs.session_cleanup.logfire.info") as mock_log_info,
        ):
            await job._run(mock_context)

        # Verify logging
        mock_log_info.assert_called_once_with("No inactive sessions found for cleanup.")

        # Verify last_cleanup_timestamp was not updated
        assert job.last_cleanup_timestamp is None

    @pytest.mark.asyncio
    async def test_run_with_sessions_to_cleanup(self, frozen_time):
        """Test run with sessions to clean up."""
        job = SessionCleanupJob()
        job._run_timestamp = frozen_time

        # Create mock sessions
        mock_session1 = MagicMock()
        mock_session1.session_id = "session1"
        mock_session1.chat_id = "chat1"

        mock_session2 = MagicMock()
        mock_session2.session_id = "session2"
        mock_session2.chat_id = "chat2"

        mock_sessions = [mock_session1, mock_session2]
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch(
                "areyouok_telegram.jobs.session_cleanup.get_all_inactive_sessions",
                new=AsyncMock(return_value=mock_sessions),
            ),
            patch.object(job, "_cleanup_session", new=AsyncMock(side_effect=[5, 3])) as mock_cleanup,
            patch("areyouok_telegram.jobs.session_cleanup.logfire.info") as mock_log_info,
            patch("areyouok_telegram.jobs.session_cleanup.logfire.span"),
        ):
            await job._run(mock_context)

        # Verify cleanup was called for each session
        assert mock_cleanup.call_count == 2
        mock_cleanup.assert_any_call(mock_session1)
        mock_cleanup.assert_any_call(mock_session2)

        # Verify logging
        mock_log_info.assert_called_with("Session cleanup completed. Deleted 8 messages from 2 sessions.")

        # Verify last_cleanup_timestamp was updated
        assert job.last_cleanup_timestamp == frozen_time

    @pytest.mark.asyncio
    async def test_run_subsequent_with_last_timestamp(self, frozen_time):
        """Test subsequent run uses last_cleanup_timestamp."""
        job = SessionCleanupJob()
        job._run_timestamp = frozen_time

        # Set a previous cleanup timestamp
        previous_cleanup = frozen_time - timedelta(hours=1)
        job.last_cleanup_timestamp = previous_cleanup

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with patch(
            "areyouok_telegram.jobs.session_cleanup.get_all_inactive_sessions", new=AsyncMock(return_value=[])
        ) as mock_get_sessions:
            await job._run(mock_context)

        # Verify it used last_cleanup_timestamp instead of 7 days
        expected_to = frozen_time - timedelta(minutes=10)
        mock_get_sessions.assert_called_once_with(from_dt=previous_cleanup, to_dt=expected_to)

    @pytest.mark.asyncio
    async def test_cleanup_session_success(self):
        """Test _cleanup_session successfully cleans up messages."""
        job = SessionCleanupJob()

        # Create mock session
        mock_session = MagicMock()
        mock_session.session_id = "session123"
        mock_session.chat_id = "chat456"
        mock_session.session_end = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)

        # Create mock messages
        mock_msg1 = MagicMock()
        mock_msg1.delete = AsyncMock(return_value=True)

        mock_msg2 = MagicMock()
        mock_msg2.delete = AsyncMock(return_value=True)

        mock_msg3 = MagicMock()
        mock_msg3.delete = AsyncMock(return_value=False)  # Deletion fails

        mock_messages = [mock_msg1, mock_msg2, mock_msg3]

        with (
            patch("areyouok_telegram.jobs.session_cleanup.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.session_cleanup.Messages.retrieve_raw_by_chat",
                new=AsyncMock(return_value=mock_messages),
            ) as mock_retrieve,
            patch("areyouok_telegram.jobs.session_cleanup.logfire.info") as mock_log_info,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            result = await job._cleanup_session(mock_session)

        # Verify correct number of messages were deleted
        assert result == 2  # Only 2 successful deletions

        # Verify Messages.retrieve_raw_by_chat was called correctly
        mock_retrieve.assert_called_once_with(db_conn=mock_db_conn, chat_id="chat456", to_time=mock_session.session_end)

        # Verify each message's delete was called
        mock_msg1.delete.assert_called_once_with(db_conn=mock_db_conn)
        mock_msg2.delete.assert_called_once_with(db_conn=mock_db_conn)
        mock_msg3.delete.assert_called_once_with(db_conn=mock_db_conn)

        # Verify logging
        mock_log_info.assert_called_once_with("Cleaned up 2 messages for session session123 in chat chat456.")

    @pytest.mark.asyncio
    async def test_cleanup_session_no_messages(self):
        """Test _cleanup_session when no messages to clean up."""
        job = SessionCleanupJob()

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        mock_session.chat_id = "chat456"
        mock_session.session_end = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)

        with (
            patch("areyouok_telegram.jobs.session_cleanup.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.session_cleanup.Messages.retrieve_raw_by_chat", new=AsyncMock(return_value=[])
            ),
            patch("areyouok_telegram.jobs.session_cleanup.logfire.info") as mock_log_info,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            result = await job._cleanup_session(mock_session)

        assert result == 0

        # Verify logging
        mock_log_info.assert_called_once_with("Cleaned up 0 messages for session session123 in chat chat456.")
