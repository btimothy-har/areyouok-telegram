"""Tests for setup/jobs.py."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from telegram.ext import Application

from areyouok_telegram.jobs import DataLogWarningJob
from areyouok_telegram.setup.jobs import restore_active_sessions
from areyouok_telegram.setup.jobs import start_data_warning_job
from areyouok_telegram.setup.jobs import start_session_cleanups


class TestRestoreActiveSessions:
    """Test the restore_active_sessions function."""

    @pytest.mark.asyncio
    async def test_restore_active_sessions_no_sessions(self):
        """Test restore_active_sessions when no active sessions exist."""
        mock_app = MagicMock(spec=Application)

        with (
            patch("areyouok_telegram.setup.jobs.async_database") as mock_async_db,
            patch("areyouok_telegram.setup.jobs.Sessions.get_all_active_sessions", new=AsyncMock(return_value=[])),
            patch("areyouok_telegram.setup.jobs.logfire.info") as mock_log,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            await restore_active_sessions(mock_app)

        mock_log.assert_called_once_with("No active sessions found, skipping conversation job setup.")

    @pytest.mark.asyncio
    async def test_restore_active_sessions_with_sessions(self, frozen_time):
        """Test restore_active_sessions with active sessions."""
        mock_app = MagicMock(spec=Application)

        # Create mock sessions
        mock_session1 = MagicMock()
        mock_session1.chat_id = "chat1"

        mock_session2 = MagicMock()
        mock_session2.chat_id = "chat2"

        mock_sessions = [mock_session1, mock_session2]

        with (
            patch("areyouok_telegram.setup.jobs.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.setup.jobs.Sessions.get_all_active_sessions",
                new=AsyncMock(return_value=mock_sessions),
            ),
            patch("areyouok_telegram.setup.jobs.schedule_job", new=AsyncMock()) as mock_schedule,
            patch("areyouok_telegram.setup.jobs.ConversationJob") as mock_conversation_job,
            patch("areyouok_telegram.setup.jobs.logfire.info") as mock_log,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            # Create mock job instances
            mock_job1 = MagicMock()
            mock_job2 = MagicMock()
            mock_conversation_job.side_effect = [mock_job1, mock_job2]

            await restore_active_sessions(mock_app)

        # Verify ConversationJob was created for each session
        assert mock_conversation_job.call_count == 2
        mock_conversation_job.assert_any_call(chat_id="chat1")
        mock_conversation_job.assert_any_call(chat_id="chat2")

        # Verify schedule_job was called for each session
        assert mock_schedule.call_count == 2
        expected_first_time = frozen_time + timedelta(seconds=5)

        mock_schedule.assert_any_call(
            context=mock_app,
            job=mock_job1,
            interval=timedelta(seconds=5),
            first=expected_first_time,
        )
        mock_schedule.assert_any_call(
            context=mock_app,
            job=mock_job2,
            interval=timedelta(seconds=5),
            first=expected_first_time,
        )

        mock_log.assert_called_once_with("Restored 2 active sessions.")


class TestStartSessionCleanups:
    """Test the start_session_cleanups function."""

    @pytest.mark.asyncio
    async def test_start_session_cleanups(self, frozen_time):  # noqa: ARG002
        """Test start_session_cleanups schedules the cleanup job."""
        mock_app = MagicMock(spec=Application)

        with (
            patch("areyouok_telegram.setup.jobs.schedule_job", new=AsyncMock()) as mock_schedule,
            patch("areyouok_telegram.setup.jobs.SessionCleanupJob") as mock_cleanup_job,
        ):
            mock_job_instance = MagicMock()
            mock_cleanup_job.return_value = mock_job_instance

            await start_session_cleanups(mock_app)

        # Verify SessionCleanupJob was created
        mock_cleanup_job.assert_called_once()

        # Verify schedule_job was called with correct parameters
        # The start time should be at the next 15-minute mark
        # frozen_time is 2025-01-01 12:00:00, so next 15-minute mark is 12:15:00
        expected_start = datetime(2025, 1, 1, 12, 15, 0, tzinfo=UTC)

        mock_schedule.assert_called_once_with(
            context=mock_app,
            job=mock_job_instance,
            interval=timedelta(minutes=15),
            first=expected_start,
        )


class TestStartDataWarningJob:
    """Test the start_data_warning_job function."""

    @pytest.mark.asyncio
    async def test_start_data_warning_job(self, frozen_time):
        """Test start_data_warning_job schedules the warning job."""
        mock_app = MagicMock(spec=Application)

        with (
            patch("areyouok_telegram.setup.jobs.schedule_job", new=AsyncMock()) as mock_schedule,
            patch("areyouok_telegram.setup.jobs.DataLogWarningJob") as mock_warning_job,
        ):
            mock_job_instance = MagicMock()
            mock_warning_job.return_value = mock_job_instance

            await start_data_warning_job(mock_app)

        # Verify DataLogWarningJob was created
        mock_warning_job.assert_called_once()

        # Verify schedule_job was called with correct parameters
        expected_start = frozen_time + timedelta(seconds=5)

        mock_schedule.assert_called_once_with(
            context=mock_app,
            job=mock_job_instance,
            interval=timedelta(minutes=5),
            first=expected_start,
        )

    @pytest.mark.asyncio
    async def test_data_warning_job_is_included_in_app_setup(self):
        """Verify DataLogWarningJob is imported and can be instantiated."""
        job = DataLogWarningJob()
        assert job.name == "data_log_warning"
