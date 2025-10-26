"""Tests for context embedding batch job."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

from areyouok_telegram.data.models import Context
from areyouok_telegram.jobs.context_embedding import ContextEmbeddingJob


@pytest.fixture
def mock_batch_size(mocker):
    """Mock RAG_BATCH_SIZE."""
    mocker.patch("areyouok_telegram.config.RAG_BATCH_SIZE", 50)


@pytest.fixture
def mock_state_persistence(mocker):
    """Mock state persistence methods."""
    mock_load = mocker.patch.object(ContextEmbeddingJob, "load_state", new_callable=AsyncMock)
    mock_save = mocker.patch.object(ContextEmbeddingJob, "save_state", new_callable=AsyncMock)
    mock_load.return_value = {}  # No previous state by default
    return {"load": mock_load, "save": mock_save}


class TestContextEmbeddingJob:
    """Tests for ContextEmbeddingJob."""

    def test_job_name(self):
        """Test job name generation."""
        job = ContextEmbeddingJob()
        assert job.name == "context_embedding"

    @pytest.mark.usefixtures("mock_batch_size", "mock_state_persistence")
    @freeze_time("2025-01-15 12:00:00")
    async def test_no_new_contexts(self, mocker, mock_state_persistence):
        """Test when no new contexts are found."""
        job = ContextEmbeddingJob()

        mocker.patch.object(
            job,
            "_fetch_new_contexts",
            return_value=[],
        )

        # Run job
        await job.run_job()

        # Verify state was loaded and saved
        mock_state_persistence["load"].assert_called_once()
        mock_state_persistence["save"].assert_called_once()

        # Verify state was saved with current time
        save_call_kwargs = mock_state_persistence["save"].call_args.kwargs
        assert "last_run_time" in save_call_kwargs
        assert save_call_kwargs["last_run_time"] == "2025-01-15T12:00:00+00:00"

    @pytest.mark.usefixtures("mock_batch_size", "mock_state_persistence")
    @freeze_time("2025-01-15 12:00:00")
    async def test_processes_batch_successfully(self, mocker, mock_state_persistence):
        """Test successful batch processing."""
        # Create mock contexts
        context1 = MagicMock(spec=Context)
        context1.id = 1
        context1.chat_id = "chat_1"
        context1.session_id = "session_1"
        context1.type = "session"  # Must match CONTEXT_TYPES_TO_EMBED
        context1.created_at = datetime(2025, 1, 15, 11, 59, 0, tzinfo=UTC)
        context1.content = "Content 1"
        context1.decrypt_content = MagicMock()

        context2 = MagicMock(spec=Context)
        context2.id = 2
        context2.chat_id = "chat_2"
        context2.session_id = "session_2"
        context2.type = "session"  # Must match CONTEXT_TYPES_TO_EMBED
        context2.created_at = datetime(2025, 1, 15, 11, 59, 30, tzinfo=UTC)
        context2.content = "Content 2"
        context2.decrypt_content = MagicMock()

        job = ContextEmbeddingJob()

        mocker.patch.object(
            job,
            "_fetch_new_contexts",
            return_value=[context1, context2],
        )
        mocker.patch.object(
            job,
            "_get_encryption_key",
            side_effect=AsyncMock(side_effect=["key1", "key2"]),
        )

        mock_pipeline = mocker.patch(
            "areyouok_telegram.jobs.context_embedding.pipeline",
        )
        mock_pipeline.arun = mocker.AsyncMock()

        # Run job
        await job.run_job()

        # Verify decryption was called
        context1.decrypt_content.assert_called_once()
        context2.decrypt_content.assert_called_once()

        # Verify pipeline was called with documents
        mock_pipeline.arun.assert_called_once()
        call_args = mock_pipeline.arun.call_args
        documents = call_args.kwargs["documents"]
        assert len(documents) == 2

        # Verify state was saved with current time and count
        save_call_kwargs = mock_state_persistence["save"].call_args.kwargs
        assert save_call_kwargs["last_run_time"] == "2025-01-15T12:00:00+00:00"
        assert save_call_kwargs["last_processed_count"] == 2

    @pytest.mark.usefixtures("mock_batch_size", "mock_state_persistence")
    @freeze_time("2025-01-15 12:00:00")
    async def test_skips_contexts_with_no_content(self, mocker, mock_state_persistence):
        """Test that contexts with no content are skipped."""
        context_valid = MagicMock(spec=Context)
        context_valid.id = 1
        context_valid.chat_id = "chat_1"
        context_valid.session_id = "session_1"
        context_valid.type = "session"  # Must match CONTEXT_TYPES_TO_EMBED
        context_valid.created_at = datetime(2025, 1, 15, 11, 59, 0, tzinfo=UTC)
        context_valid.content = "Valid content"
        context_valid.decrypt_content = MagicMock()

        context_invalid = MagicMock(spec=Context)
        context_invalid.id = 2
        context_invalid.chat_id = "chat_2"
        context_invalid.session_id = "session_2"
        context_invalid.type = "session"  # Must match CONTEXT_TYPES_TO_EMBED
        context_invalid.created_at = datetime(2025, 1, 15, 11, 59, 30, tzinfo=UTC)
        context_invalid.content = None
        context_invalid.decrypt_content = MagicMock()

        job = ContextEmbeddingJob()

        mocker.patch.object(
            job,
            "_fetch_new_contexts",
            return_value=[context_valid, context_invalid],
        )
        mocker.patch.object(
            job,
            "_get_encryption_key",
            return_value=AsyncMock(return_value="key1"),
        )

        mock_pipeline = mocker.patch(
            "areyouok_telegram.jobs.context_embedding.pipeline",
        )
        mock_pipeline.arun = mocker.AsyncMock()

        # Run job
        await job.run_job()

        # Verify only one document was processed
        call_args = mock_pipeline.arun.call_args
        documents = call_args.kwargs["documents"]
        assert len(documents) == 1

        # Verify state was saved with one document
        save_call_kwargs = mock_state_persistence["save"].call_args.kwargs
        assert save_call_kwargs["last_processed_count"] == 1

    @pytest.mark.usefixtures("mock_batch_size")
    @freeze_time("2025-01-15 12:00:00")
    async def test_loads_previous_state(self, mocker):
        """Test that job loads and uses previous state."""
        job = ContextEmbeddingJob()

        # Mock previous state
        previous_run_time = "2025-01-15T11:00:00+00:00"
        mock_load = mocker.patch.object(
            job,
            "load_state",
            new_callable=AsyncMock,
            return_value={"last_run_time": previous_run_time},
        )
        mock_save = mocker.patch.object(job, "save_state", new_callable=AsyncMock)

        # Mock that contexts will be fetched from the previous run time
        mock_fetch = mocker.patch.object(job, "_fetch_new_contexts", new_callable=AsyncMock, return_value=[])

        # Run job
        await job.run_job()

        # Verify state was loaded
        mock_load.assert_called_once()

        # Verify fetch was called with the previous run time
        mock_fetch.assert_called_once()
        call_args = mock_fetch.call_args
        from_timestamp_arg = call_args.kwargs["from_timestamp"]
        to_timestamp_arg = call_args.kwargs["to_timestamp"]
        assert from_timestamp_arg == datetime.fromisoformat(previous_run_time)
        assert to_timestamp_arg == datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

        # Verify new state was saved
        mock_save.assert_called_once()

    @freeze_time("2025-01-15 12:00:00")
    async def test_fetch_new_contexts(self, mocker):
        """Test fetching contexts from database."""
        context1 = MagicMock(spec=Context)
        context1.id = 1
        context1.chat_id = "chat_1"

        context2 = MagicMock(spec=Context)
        context2.id = 2
        context2.chat_id = "chat_2"

        job = ContextEmbeddingJob()

        mocker.patch(
            "areyouok_telegram.jobs.context_embedding.Context.get_by_created_timestamp",
            return_value=[context1, context2],
        )

        from_time = datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)
        to_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        result = await job._fetch_new_contexts(from_timestamp=from_time, to_timestamp=to_time)

        assert len(result) == 2
        assert result[0] == context1
        assert result[1] == context2
