"""Tests for jobs/ping.py."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time
from telegram.ext import ContextTypes

from areyouok_telegram.jobs.ping import PingJob


class TestPingJob:
    """Test the PingJob class."""

    def test_init(self, frozen_time):
        """Test PingJob initialization."""
        job = PingJob()

        # Should inherit from BaseJob
        assert job._bot_id is None
        assert job._run_count == 0
        assert isinstance(job._run_timestamp, datetime)
        assert job._run_timestamp.tzinfo == UTC
        # Should have startup_time initialized
        assert job._startup_time == frozen_time

    def test_name_property(self):
        """Test job name property."""
        job = PingJob()
        assert job.name == "ping_status"

    @pytest.mark.asyncio
    async def test_run_executes_successfully(self, frozen_time):
        """Test run_job method executes successfully and calls bot.get_me."""
        job = PingJob()

        # Create mock bot info
        mock_bot_info = MagicMock()
        mock_bot_info.id = 123456789
        mock_bot_info.username = "test_bot"
        mock_bot_info.first_name = "Test Bot"

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.get_me = AsyncMock(return_value=mock_bot_info)
        mock_context.bot.id = mock_bot_info.id
        mock_context.job_queue.jobs.return_value = [MagicMock(), MagicMock(), MagicMock()]  # 3 mock jobs

        # Run the job (this will call run_job internally and set up the context)
        await job.run(mock_context)

        # Verify bot.get_me was called
        mock_context.bot.get_me.assert_called()

        # Verify job has correct uptime tracking
        assert hasattr(job, "_startup_time")
        assert job._startup_time == frozen_time

    @pytest.mark.asyncio
    async def test_run_increments_count(self):
        """Test that run_count increments with each run."""
        job = PingJob()

        # Create mock bot info
        mock_bot_info = MagicMock()
        mock_bot_info.id = 123456789
        mock_bot_info.username = "test_bot"
        mock_bot_info.first_name = "Test Bot"

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.get_me = AsyncMock(return_value=mock_bot_info)
        mock_context.bot.id = mock_bot_info.id
        mock_context.job_queue.jobs.return_value = []

        assert job._run_count == 0

        # First run
        await job.run(mock_context)
        assert job._run_count == 1

        # Second run
        await job.run(mock_context)
        assert job._run_count == 2

        # Third run
        await job.run(mock_context)
        assert job._run_count == 3

    @pytest.mark.asyncio
    async def test_run_updates_timestamp(self, frozen_time):
        """Test that run_timestamp updates with each run."""
        job = PingJob()

        # Create mock bot info
        mock_bot_info = MagicMock()
        mock_bot_info.id = 123456789
        mock_bot_info.username = "test_bot"
        mock_bot_info.first_name = "Test Bot"

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.get_me = AsyncMock(return_value=mock_bot_info)
        mock_context.bot.id = mock_bot_info.id
        mock_context.job_queue.jobs.return_value = []

        # Run the job
        await job.run(mock_context)

        # Verify timestamp was updated
        assert job._run_timestamp == frozen_time

    @pytest.mark.asyncio
    async def test_job_queue_size_check(self):
        """Test job correctly accesses job queue size."""
        job = PingJob()

        # Create mock bot info
        mock_bot_info = MagicMock()
        mock_bot_info.id = 123456789
        mock_bot_info.username = "test_bot"
        mock_bot_info.first_name = "Test Bot"

        # Create mock context with empty job queue
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.get_me = AsyncMock(return_value=mock_bot_info)
        mock_context.bot.id = mock_bot_info.id
        mock_context.job_queue.jobs.return_value = []  # Empty queue

        # Run the job (this sets up context and calls run_job internally)
        await job.run(mock_context)

        # Verify job_queue.jobs was called to get queue size
        mock_context.job_queue.jobs.assert_called_once()

    @pytest.mark.asyncio
    async def test_uptime_calculation(self):
        """Test that uptime is calculated correctly."""
        start_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        with freeze_time(start_time) as frozen_time:
            job = PingJob()
            assert job._startup_time == start_time

            # Create mock bot info
            mock_bot_info = MagicMock()
            mock_bot_info.id = 123456789
            mock_bot_info.username = "test_bot"
            mock_bot_info.first_name = "Test Bot"

            # Create mock context
            mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
            mock_context.bot.get_me = AsyncMock(return_value=mock_bot_info)
            mock_context.bot.id = mock_bot_info.id
            mock_context.job_queue.jobs.return_value = []

            # Advance time by 1 hour and 30 minutes
            frozen_time.tick(delta=timedelta(hours=1, minutes=30))
            current_time = datetime.now(UTC)

            # Run the job (this sets up context and calls run_job internally)
            await job.run(mock_context)

            # Verify uptime calculation would be correct
            expected_uptime = current_time - job._startup_time
            assert expected_uptime == timedelta(hours=1, minutes=30)
