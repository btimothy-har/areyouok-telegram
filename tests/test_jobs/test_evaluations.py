"""Tests for jobs/evaluations.py - minimal core functionality tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from areyouok_telegram.jobs.evaluations import EvaluationsJob, get_generation_by_id_cached, GEN_CACHE


class TestGetGenerationByIdCached:
    """Test the get_generation_by_id_cached function."""

    def setup_method(self):
        """Clear cache before each test."""
        GEN_CACHE.clear()

    @pytest.mark.asyncio
    async def test_get_generation_by_id_cached_cache_miss(self):
        """Test cache miss fetches from database."""
        mock_generation = MagicMock()
        mock_generation.id = 1

        with patch("areyouok_telegram.data.models.LLMGeneration.get_by_id", new=AsyncMock(return_value=mock_generation)):
            result = await get_generation_by_id_cached(gen_id=1)

            assert result == mock_generation
            assert GEN_CACHE[1] == mock_generation

    @pytest.mark.asyncio
    async def test_get_generation_by_id_cached_cache_hit(self):
        """Test cache hit returns cached value."""
        mock_generation = MagicMock()
        mock_generation.id = 2
        GEN_CACHE[2] = mock_generation

        with patch("areyouok_telegram.data.models.LLMGeneration.get_by_id", new=AsyncMock()) as mock_get:
            result = await get_generation_by_id_cached(gen_id=2)

            assert result == mock_generation
            # Should not call database
            mock_get.assert_not_called()


class TestEvaluationsJob:
    """Test the EvaluationsJob class core functionality."""

    def test_init(self):
        """Test EvaluationsJob initialization."""
        job = EvaluationsJob(chat_id=123, session_id=456)
        assert job.chat_id == 123
        assert job.session_id == 456

    def test_name_property(self):
        """Test name property."""
        job = EvaluationsJob(chat_id=789, session_id=101)
        assert job.name == "evaluations:101"

    @pytest.mark.asyncio
    async def test_run_job_no_generations(self, chat_factory):
        """Test run_job when no generations found."""
        job = EvaluationsJob(chat_id=123, session_id=456)
        mock_chat = chat_factory(id_value=123)
        mock_session = MagicMock()
        mock_session.id = 456

        with (
            patch("areyouok_telegram.data.models.Chat.get_by_id", new=AsyncMock(return_value=mock_chat)),
            patch("areyouok_telegram.data.models.Session.get_by_id", new=AsyncMock(return_value=mock_session)),
            patch("areyouok_telegram.data.models.LLMGeneration.get_by_session", new=AsyncMock(return_value=[])),
        ):
            await job.run_job()
            # Test passes if no exceptions (logs warning and returns)
