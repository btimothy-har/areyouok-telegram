"""Tests for the SessionCleanupJob class and start_session_cleanups function."""

import hashlib
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from areyouok_telegram.jobs.session_cleanup import SessionCleanupJob
from areyouok_telegram.setup.jobs import start_session_cleanups


@pytest.fixture
def mock_session_cleanup_job():
    """Create a mock SessionCleanupJob instance."""
    job = SessionCleanupJob()
    return job


@pytest.fixture
def mock_inactive_sessions():
    """Create mock inactive session objects."""
    session1 = MagicMock()
    session1.chat_id = "123456"
    session1.session_end = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

    session2 = MagicMock()
    session2.chat_id = "789012"
    session2.session_end = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

    return [session1, session2]


@pytest.fixture
def mock_messages():
    """Create mock message objects."""
    msg1 = MagicMock()
    msg1.delete = AsyncMock(return_value=True)

    msg2 = MagicMock()
    msg2.delete = AsyncMock(return_value=True)

    msg3 = MagicMock()
    msg3.delete = AsyncMock(return_value=False)  # Failed deletion

    return [msg1, msg2, msg3]


class TestSessionCleanupJob:
    """Test the SessionCleanupJob class."""

    def test_init(self, mock_session_cleanup_job):
        """Test initialization of SessionCleanupJob."""
        assert mock_session_cleanup_job.last_cleanup_timestamp is None

    def test_name_property(self, mock_session_cleanup_job):
        """Test the name property."""
        assert mock_session_cleanup_job.name == "session_cleanup"

    def test_id_property(self, mock_session_cleanup_job):
        """Test the _id property returns MD5 hash of name."""
        expected_id = hashlib.md5(b"session_cleanup").hexdigest()
        assert mock_session_cleanup_job._id == expected_id

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 12:00:00", tz_offset=0)
    async def test_run_first_time_no_sessions(self, mock_session_cleanup_job):
        """Test run method when it's first time and no sessions found."""
        context = MagicMock()

        with patch(
            "areyouok_telegram.jobs.session_cleanup.Sessions.get_all_inactive_sessions", new=AsyncMock()
        ) as mock_get_sessions:
            mock_get_sessions.return_value = []

            await mock_session_cleanup_job.run(context)

            # Should look for sessions from 7 days ago since no last cleanup timestamp
            expected_since = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC) - timedelta(days=7)
            expected_to = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC) - timedelta(minutes=10)

            mock_get_sessions.assert_called_once()
            call_args = mock_get_sessions.call_args
            # Verify the time range parameters
            assert call_args.kwargs["from_dt"] == expected_since
            assert call_args.kwargs["to_dt"] == expected_to

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 12:00:00", tz_offset=0)
    async def test_run_with_existing_timestamp(self, mock_session_cleanup_job):
        """Test run method when there's an existing cleanup timestamp."""
        context = MagicMock()

        # Set existing cleanup timestamp
        mock_session_cleanup_job.last_cleanup_timestamp = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        with patch(
            "areyouok_telegram.jobs.session_cleanup.Sessions.get_all_inactive_sessions", new=AsyncMock()
        ) as mock_get_sessions:
            mock_get_sessions.return_value = []

            await mock_session_cleanup_job.run(context)

            # Should use existing timestamp as the start time
            expected_since = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
            expected_to = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC) - timedelta(minutes=10)

            call_args = mock_get_sessions.call_args
            assert call_args.kwargs["from_dt"] == expected_since
            assert call_args.kwargs["to_dt"] == expected_to

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 12:00:00", tz_offset=0)
    async def test_run_applies_safety_margin(self, mock_session_cleanup_job):
        """Test that run method applies 10-minute safety margin."""
        context = MagicMock()

        with patch(
            "areyouok_telegram.jobs.session_cleanup.Sessions.get_all_inactive_sessions", new=AsyncMock()
        ) as mock_get_sessions:
            mock_get_sessions.return_value = []

            await mock_session_cleanup_job.run(context)

            # Should exclude sessions ended within last 10 minutes
            current_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
            expected_to = current_time - timedelta(minutes=10)

            call_args = mock_get_sessions.call_args
            assert call_args.kwargs["to_dt"] == expected_to

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 12:00:00", tz_offset=0)
    async def test_run_with_sessions_to_cleanup(self, mock_session_cleanup_job, mock_inactive_sessions):
        """Test run method when there are sessions to clean up."""
        context = MagicMock()

        with (
            patch(
                "areyouok_telegram.jobs.session_cleanup.Sessions.get_all_inactive_sessions", new=AsyncMock()
            ) as mock_get_sessions,
            patch.object(mock_session_cleanup_job, "_cleanup_session", new=AsyncMock()) as mock_cleanup_session,
        ):
            mock_get_sessions.return_value = mock_inactive_sessions
            mock_cleanup_session.side_effect = [5, 3]  # Return deleted message counts

            await mock_session_cleanup_job.run(context)

            # Should call _cleanup_session for each session
            assert mock_cleanup_session.call_count == 2
            mock_cleanup_session.assert_any_call(mock_inactive_sessions[0])
            mock_cleanup_session.assert_any_call(mock_inactive_sessions[1])

            # Should update last cleanup timestamp
            assert mock_session_cleanup_job.last_cleanup_timestamp == datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_cleanup_session_success(self, mock_session_cleanup_job, mock_messages):
        """Test _cleanup_session method successful message deletion."""
        session = MagicMock()
        session.chat_id = "123456"
        session.session_end = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        with patch(
            "areyouok_telegram.jobs.session_cleanup.Messages.retrieve_raw_by_chat", new=AsyncMock()
        ) as mock_retrieve:
            mock_retrieve.return_value = mock_messages

            result = await mock_session_cleanup_job._cleanup_session(session)

            # Should return count of successfully deleted messages (2 out of 3)
            assert result == 2

            # Should call delete on all messages
            for msg in mock_messages:
                msg.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_session_no_messages(self, mock_session_cleanup_job):
        """Test _cleanup_session method when no messages exist."""
        session = MagicMock()
        session.chat_id = "123456"
        session.session_end = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        with patch(
            "areyouok_telegram.jobs.session_cleanup.Messages.retrieve_raw_by_chat", new=AsyncMock()
        ) as mock_retrieve:
            mock_retrieve.return_value = []

            result = await mock_session_cleanup_job._cleanup_session(session)

            # Should return 0 when no messages
            assert result == 0

    @pytest.mark.asyncio
    async def test_cleanup_session_uses_separate_connection(self, mock_session_cleanup_job):
        """Test _cleanup_session creates its own database connection."""
        session = MagicMock()
        session.chat_id = "123456"
        session.session_end = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        with (
            patch("areyouok_telegram.jobs.session_cleanup.async_database_session") as mock_db_session,
            patch(
                "areyouok_telegram.jobs.session_cleanup.Messages.retrieve_raw_by_chat", new=AsyncMock()
            ) as mock_retrieve,
        ):
            mock_conn = AsyncMock()
            mock_db_session.return_value.__aenter__.return_value = mock_conn
            mock_retrieve.return_value = []

            await mock_session_cleanup_job._cleanup_session(session)

            # Should use the connection for message retrieval
            mock_retrieve.assert_called_once_with(
                session=mock_conn,
                chat_id="123456",
                to_time=session.session_end,
            )


class TestStartSessionCleanups:
    """Test the start_session_cleanups function."""

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 12:07:30", tz_offset=0)
    async def test_start_session_cleanups_scheduling(self):
        """Test start_session_cleanups schedules job correctly."""
        context = MagicMock()
        context.job_queue.run_repeating = MagicMock()

        await start_session_cleanups(context)

        # Should schedule the job
        context.job_queue.run_repeating.assert_called_once()
        call_args = context.job_queue.run_repeating.call_args

        # Check scheduling parameters
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
        context = MagicMock()
        context.job_queue.run_repeating = MagicMock()

        await start_session_cleanups(context)

        call_args = context.job_queue.run_repeating.call_args

        # Should start at next 15-minute mark (12:15:00)
        expected_start = datetime(2025, 1, 15, 12, 15, 0, tzinfo=UTC)
        assert call_args.kwargs["first"] == expected_start

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 12:22:45", tz_offset=0)
    async def test_start_session_cleanups_middle_of_interval(self):
        """Test scheduling when current time is in middle of 15-minute interval."""
        context = MagicMock()
        context.job_queue.run_repeating = MagicMock()

        await start_session_cleanups(context)

        call_args = context.job_queue.run_repeating.call_args

        # Should start at next 15-minute mark (12:30:00)
        expected_start = datetime(2025, 1, 15, 12, 30, 0, tzinfo=UTC)
        assert call_args.kwargs["first"] == expected_start

    @pytest.mark.asyncio
    async def test_start_session_cleanups_creates_job_instance(self):
        """Test that start_session_cleanups creates SessionCleanupJob instance."""
        context = MagicMock()

        with patch("areyouok_telegram.setup.jobs.SessionCleanupJob") as mock_job_class:
            mock_job_instance = MagicMock()
            mock_job_instance.name = "session_cleanup"
            mock_job_instance._id = "test_id"
            mock_job_class.return_value = mock_job_instance

            await start_session_cleanups(context)

            # Should create SessionCleanupJob instance
            mock_job_class.assert_called_once()

            # Should use job instance's run method
            call_args = context.job_queue.run_repeating.call_args
            assert call_args.args[0] == mock_job_instance.run
