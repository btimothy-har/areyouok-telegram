"""Tests for jobs/base.py."""

import asyncio
import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ContextTypes

from areyouok_telegram.jobs.base import JOB_LOCK, BaseJob


class ConcreteJob(BaseJob):
    """Concrete implementation of BaseJob for testing."""

    @property
    def name(self) -> str:
        return "test_job"

    async def run_job(self) -> None:
        """Test implementation of run_job."""
        pass


class TestBaseJob:
    """Test the BaseJob abstract class."""

    def test_init(self):
        """Test BaseJob initialization."""
        job = ConcreteJob()

        assert job._bot_id is None
        assert job._run_count == 0
        assert job._run_context is None
        assert isinstance(job._run_timestamp, datetime)
        assert job._run_timestamp.tzinfo == UTC

    def test_id_property(self):
        """Test job ID is consistent MD5 hash of name."""

        job = ConcreteJob()

        # ID should be MD5 hash of name
        expected_id = hashlib.md5(b"test_job").hexdigest()
        assert job.id == expected_id

        # ID should be consistent
        assert job.id == job.id

    def test_name_property(self):
        """Test name property is implemented."""
        job = ConcreteJob()
        assert job.name == "test_job"

    @pytest.mark.asyncio
    async def test_run_updates_state(self, frozen_time):
        """Test run method updates internal state."""
        job = ConcreteJob()

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"

        # Run the job
        await job.run(mock_context)

        # Verify state was updated
        assert job._bot_id == "bot123"
        assert job._run_count == 1
        assert job._run_context == mock_context
        assert job._run_timestamp == frozen_time

        # Run again to verify count increments
        await job.run(mock_context)
        assert job._run_count == 2

    @pytest.mark.asyncio
    async def test_run_calls_internal_run(self):
        """Test run method calls run_job implementation."""
        job = ConcreteJob()
        job.run_job = AsyncMock()

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"

        await job.run(mock_context)

        job.run_job.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_stop_removes_jobs(self):
        """Test stop method removes all scheduled jobs."""
        job = ConcreteJob()

        # Create mock jobs
        mock_job1 = MagicMock()
        mock_job2 = MagicMock()

        # Create mock context and simulate it being set during run
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.job_queue.get_jobs_by_name.return_value = [mock_job1, mock_job2]
        job._run_context = mock_context  # Simulate context being set

        with patch("areyouok_telegram.jobs.base.logfire.info") as mock_log_info:
            await job.stop()

        # Verify jobs were retrieved by name
        mock_context.job_queue.get_jobs_by_name.assert_called_once_with("test_job")

        # Verify each job was scheduled for removal
        mock_job1.schedule_removal.assert_called_once()
        mock_job2.schedule_removal.assert_called_once()

        # Verify logging
        mock_log_info.assert_called_once_with("Scheduled job test_job is now stopped.")

    @pytest.mark.asyncio
    async def test_stop_no_existing_jobs(self):
        """Test stop method when no jobs exist."""
        job = ConcreteJob()

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.job_queue.get_jobs_by_name.return_value = []
        job._run_context = mock_context  # Simulate context being set

        with patch("areyouok_telegram.jobs.base.logfire.warning") as mock_log_warning:
            await job.stop()

        # Verify warning was logged
        mock_log_warning.assert_called_once_with("No existing job found for test_job, nothing to stop.")

    @pytest.mark.asyncio
    async def test_stop_uses_lock(self):
        """Test stop method uses job-specific lock."""
        job = ConcreteJob()

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_job = MagicMock()
        mock_context.job_queue.get_jobs_by_name.return_value = [mock_job]
        job._run_context = mock_context  # Simulate context being set

        # Get the lock for this job
        job_lock = JOB_LOCK[job.id]

        # Verify the lock is not initially locked
        assert not job_lock.locked()

        lock_was_acquired = False

        def check_lock(name):  # noqa: ARG001
            # When get_jobs_by_name is called, the lock should be held
            nonlocal lock_was_acquired
            lock_was_acquired = job_lock.locked()
            return [mock_job]

        mock_context.job_queue.get_jobs_by_name.side_effect = check_lock

        with patch("areyouok_telegram.jobs.base.logfire.info"):
            await job.stop()

        # Verify lock was acquired during execution
        assert lock_was_acquired
        # After stop, lock should be released
        assert not job_lock.locked()

    @pytest.mark.asyncio
    async def test_abstract_methods_not_implemented(self):
        """Test abstract methods raise NotImplementedError."""

        # Create a job without implementing abstract methods
        class IncompleteJob(BaseJob):
            pass

        # Should not be able to instantiate
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteJob()

    @pytest.mark.asyncio
    async def test_stop_with_no_custom_stop(self):
        """Test stop method works without custom _stop."""
        job = ConcreteJob()

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.job_queue.get_jobs_by_name.return_value = []
        job._run_context = mock_context  # Simulate context being set

        with patch("areyouok_telegram.jobs.base.logfire.warning") as mock_warning:
            await job.stop()

        # Should log warning about no jobs
        mock_warning.assert_called_once()

    def test_job_lock_is_defaultdict(self):
        """Test JOB_LOCK is a defaultdict creating asyncio.Lock instances."""
        # JOB_LOCK should create new locks for new keys
        test_lock = JOB_LOCK["new_test_key"]
        assert isinstance(test_lock, asyncio.Lock)

        # Same key should return same lock
        assert JOB_LOCK["new_test_key"] is test_lock
