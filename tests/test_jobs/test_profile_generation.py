"""Tests for jobs/profile_generation.py - minimal core functionality tests."""

from unittest.mock import AsyncMock, patch

import pytest

from areyouok_telegram.jobs.profile_generation import ProfileGenerationJob


class TestProfileGenerationJob:
    """Test the ProfileGenerationJob class core functionality."""

    def test_init(self):
        """Test ProfileGenerationJob initialization."""
        job = ProfileGenerationJob()
        assert job._bot_id is None
        assert job._run_count == 0

    def test_name_property(self):
        """Test name property."""
        job = ProfileGenerationJob()
        assert job.name == "profile_generation"

    @pytest.mark.asyncio
    async def test_run_job_basic_execution(self):
        """Test run_job executes without errors with mocked dependencies."""
        job = ProfileGenerationJob()

        with (
            patch("areyouok_telegram.data.models.Chat.get", new=AsyncMock(return_value=[])),
            patch("areyouok_telegram.data.models.JobState.get", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.data.models.JobState.save", new=AsyncMock()),
        ):
            await job.run_job()
            # Test passes if no exceptions
