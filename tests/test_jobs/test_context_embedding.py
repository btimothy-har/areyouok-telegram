"""Tests for context embedding batch job - minimal core functionality tests."""

from unittest.mock import AsyncMock, patch

import pytest

from areyouok_telegram.jobs.context_embedding import ContextEmbeddingJob


class TestContextEmbeddingJob:
    """Test the ContextEmbeddingJob class core functionality."""

    def test_init(self):
        """Test ContextEmbeddingJob initialization."""
        job = ContextEmbeddingJob()
        assert job._bot_id is None

    def test_name_property(self):
        """Test name property."""
        job = ContextEmbeddingJob()
        assert job.name == "context_embedding"

    @pytest.mark.asyncio
    async def test_run_job_basic_execution(self):
        """Test run_job executes without errors with mocked dependencies."""
        job = ContextEmbeddingJob()

        with (
            patch("areyouok_telegram.data.models.Chat.get", new=AsyncMock(return_value=[])),
            patch("areyouok_telegram.data.models.Context.get_by_chat", new=AsyncMock(return_value=[])),
            patch(
                "areyouok_telegram.jobs.context_embedding.ContextEmbeddingJob.load_state",
                new=AsyncMock(return_value={}),
            ),
            patch("areyouok_telegram.jobs.context_embedding.ContextEmbeddingJob.save_state", new=AsyncMock()),
        ):
            await job.run_job()
            # Test passes if no exceptions
