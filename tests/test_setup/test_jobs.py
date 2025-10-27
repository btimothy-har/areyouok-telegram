"""Tests for setup/jobs.py."""

from unittest.mock import MagicMock, patch

import pytest
from telegram.ext import Application

from areyouok_telegram.jobs import DataLogWarningJob, PingJob
from areyouok_telegram.setup.jobs import start_data_warning_job, start_ping_job


class TestStartDataWarningJob:
    """Test the start_data_warning_job function."""

    @pytest.mark.asyncio
    async def test_start_data_warning_job(self):
        """Test starting the data warning job."""
        mock_app = MagicMock(spec=Application)
        await start_data_warning_job(mock_app)
        # Test passes if no exceptions

    def test_data_warning_job_is_included_in_app_setup(self):
        """Verify DataLogWarningJob is imported and can be instantiated."""
        job = DataLogWarningJob()
        assert job.name == "data_log_warning"


class TestStartPingJob:
    """Test the start_ping_job function."""

    @pytest.mark.asyncio
    async def test_start_ping_job(self):
        """Test starting the ping job."""
        mock_app = MagicMock(spec=Application)

        with patch("areyouok_telegram.setup.jobs.schedule_job"):
            await start_ping_job(mock_app)
            # Test passes if no exceptions

    def test_ping_job_is_included_in_app_setup(self):
        """Verify PingJob is imported and can be instantiated."""
        job = PingJob()
        assert job.name == "ping_status"
