"""Tests for the setup.jobs module."""

import hashlib
from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from telegram.ext import Application

from areyouok_telegram.setup.jobs import restore_active_sessions
from areyouok_telegram.setup.jobs import start_session_cleanups


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
            patch("areyouok_telegram.setup.jobs.async_database_session") as mock_db_session,
            patch("areyouok_telegram.setup.jobs.Sessions.get_all_active_sessions") as mock_get_sessions,
            patch("areyouok_telegram.setup.jobs.schedule_conversation_job") as mock_schedule_job,
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
            patch("areyouok_telegram.setup.jobs.async_database_session") as mock_db_session,
            patch("areyouok_telegram.setup.jobs.Sessions.get_all_active_sessions") as mock_get_sessions,
            patch("areyouok_telegram.setup.jobs.schedule_conversation_job") as mock_schedule_job,
        ):
            # Configure mocks
            mock_db_session.return_value.__aenter__.return_value = AsyncMock()
            mock_get_sessions.return_value = []  # No active sessions

            # Act
            await restore_active_sessions(mock_context)

            # Assert
            mock_get_sessions.assert_called_once_with(mock_db_session.return_value.__aenter__.return_value)
            mock_schedule_job.assert_not_called()


class TestStartSessionCleanups:
    """Test the start_session_cleanups function."""

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 12:07:30", tz_offset=0)
    async def test_start_session_cleanups_schedules_job(self):
        """Test start_session_cleanups schedules the cleanup job correctly."""
        # Arrange
        mock_context = MagicMock(spec=Application)
        mock_context.job_queue.run_repeating = MagicMock()

        with patch("areyouok_telegram.setup.jobs.SessionCleanupJob") as mock_job_class:
            mock_job_instance = MagicMock()
            mock_job_instance.name = "session_cleanup"
            mock_job_instance._id = hashlib.md5(b"session_cleanup").hexdigest()
            mock_job_instance.run = MagicMock()
            mock_job_class.return_value = mock_job_instance

            # Act
            await start_session_cleanups(mock_context)

            # Assert
            # Should create SessionCleanupJob instance
            mock_job_class.assert_called_once()

            # Should schedule the job
            mock_context.job_queue.run_repeating.assert_called_once()
            call_args = mock_context.job_queue.run_repeating.call_args

            # Check scheduling parameters
            assert call_args.args[0] == mock_job_instance.run
            assert call_args.kwargs["interval"] == 15 * 60  # 15 minutes
            assert call_args.kwargs["name"] == "session_cleanup"

            # Should start at next 15-minute mark (12:15:00 in this case)
            expected_start = datetime(2025, 1, 15, 12, 15, 0, tzinfo=UTC)
            assert call_args.kwargs["first"] == expected_start

            # Check job kwargs
            expected_id = hashlib.md5(b"session_cleanup").hexdigest()
            assert call_args.kwargs["job_kwargs"]["id"] == expected_id
            assert call_args.kwargs["job_kwargs"]["coalesce"] is True
            assert call_args.kwargs["job_kwargs"]["max_instances"] == 1

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 12:00:00", tz_offset=0)
    async def test_start_session_cleanups_exact_15_minute_mark(self):
        """Test scheduling when current time is exactly on 15-minute mark."""
        # Arrange
        mock_context = MagicMock(spec=Application)
        mock_context.job_queue.run_repeating = MagicMock()

        with patch("areyouok_telegram.setup.jobs.SessionCleanupJob") as mock_job_class:
            mock_job_instance = MagicMock()
            mock_job_instance.name = "session_cleanup"
            mock_job_instance._id = "test_id"
            mock_job_class.return_value = mock_job_instance

            # Act
            await start_session_cleanups(mock_context)

            # Assert
            call_args = mock_context.job_queue.run_repeating.call_args

            # Should start at next 15-minute mark (12:15:00)
            expected_start = datetime(2025, 1, 15, 12, 15, 0, tzinfo=UTC)
            assert call_args.kwargs["first"] == expected_start

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 12:22:45", tz_offset=0)
    async def test_start_session_cleanups_middle_of_interval(self):
        """Test scheduling when current time is in middle of 15-minute interval."""
        # Arrange
        mock_context = MagicMock(spec=Application)
        mock_context.job_queue.run_repeating = MagicMock()

        with patch("areyouok_telegram.setup.jobs.SessionCleanupJob") as mock_job_class:
            mock_job_instance = MagicMock()
            mock_job_instance.name = "session_cleanup"
            mock_job_instance._id = "test_id"
            mock_job_class.return_value = mock_job_instance

            # Act
            await start_session_cleanups(mock_context)

            # Assert
            call_args = mock_context.job_queue.run_repeating.call_args

            # Should start at next 15-minute mark (12:30:00)
            expected_start = datetime(2025, 1, 15, 12, 30, 0, tzinfo=UTC)
            assert call_args.kwargs["first"] == expected_start
