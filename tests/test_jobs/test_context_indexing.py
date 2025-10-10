"""Tests for context indexing job."""

from unittest.mock import MagicMock

import pytest

from areyouok_telegram.data import Chats
from areyouok_telegram.data import Context
from areyouok_telegram.jobs.context_indexing import ContextIndexingJob


@pytest.fixture
def mock_rag_enabled(mocker):
    """Mock RAG_ENABLE_SEMANTIC_SEARCH to True."""
    mocker.patch("areyouok_telegram.jobs.context_indexing.RAG_ENABLE_SEMANTIC_SEARCH", new=True)


class TestContextIndexingJob:
    """Tests for ContextIndexingJob."""

    def test_job_name(self):
        """Test job name generation."""
        job = ContextIndexingJob(context_id=123)
        assert job.name == "context_indexing:123"

    async def test_skips_when_rag_disabled(self, mocker):
        """Test that job skips indexing when RAG is disabled."""
        mocker.patch("areyouok_telegram.jobs.context_indexing.RAG_ENABLE_SEMANTIC_SEARCH", new=False)

        job = ContextIndexingJob(context_id=123)

        # Should not raise any errors
        await job.run_job()

    @pytest.mark.usefixtures("mock_rag_enabled")
    async def test_skips_when_context_not_found(self, mocker):
        """Test that job skips when context is not found."""
        job = ContextIndexingJob(context_id=999)

        # Mock fetch to return None
        mocker.patch.object(
            job,
            "_fetch_context_and_key",
            return_value=(None, None),
        )

        # Should not raise errors
        await job.run_job()

    @pytest.mark.usefixtures("mock_rag_enabled")
    async def test_skips_when_no_content(self, mocker):
        """Test that job skips when context has no content."""
        context = MagicMock(spec=Context)
        context.id = 123
        context.decrypt_content = MagicMock(return_value=None)
        chat_key = "test_key"

        job = ContextIndexingJob(context_id=123)

        mocker.patch.object(
            job,
            "_fetch_context_and_key",
            return_value=(context, chat_key),
        )

        # Should not raise errors
        await job.run_job()

    @pytest.mark.usefixtures("mock_rag_enabled")
    async def test_indexes_context_successfully(self, mocker):
        """Test successful context indexing."""
        context = MagicMock(spec=Context)
        context.id = 123
        context.chat_id = "chat_123"
        context.session_id = "session_456"
        context.decrypt_content = MagicMock(return_value="This is test content")

        chat_key = "test_key"
        decrypted_content = "This is test content"

        job = ContextIndexingJob(context_id=123)

        mocker.patch.object(
            job,
            "_fetch_context_and_key",
            return_value=(context, chat_key),
        )

        mock_create_document = mocker.patch(
            "areyouok_telegram.jobs.context_indexing.create_context_document",
        )
        mock_document = mocker.Mock()
        mock_create_document.return_value = mock_document

        mock_index = mocker.patch(
            "areyouok_telegram.jobs.context_indexing.context_index",
        )
        # Make ainsert awaitable
        mock_index.ainsert = mocker.AsyncMock()

        # Run the job
        await job.run_job()

        # Verify document creation
        mock_create_document.assert_called_once_with(context, decrypted_content)

        # Verify insertion
        mock_index.ainsert.assert_called_once_with(mock_document)

    async def test_fetch_context_and_key(self, mocker):
        """Test fetching context and encryption key."""
        context = MagicMock(spec=Context)
        context.id = 123
        context.chat_id = "chat_123"

        chat = MagicMock(spec=Chats)
        chat.chat_id = "chat_123"
        chat.retrieve_key = MagicMock(return_value="test_encryption_key")

        chat_key = "test_encryption_key"

        job = ContextIndexingJob(context_id=123)

        # Mock Context.get_by_ids
        mocker.patch(
            "areyouok_telegram.jobs.context_indexing.Context.get_by_ids",
            return_value=[context],
        )

        # Mock Chats.get_by_id
        mocker.patch(
            "areyouok_telegram.jobs.context_indexing.Chats.get_by_id",
            return_value=chat,
        )

        # Call the method
        result_context, result_key = await job._fetch_context_and_key()

        assert result_context == context
        assert result_key == chat_key

    async def test_fetch_context_and_key_context_not_found(self, mocker):
        """Test when context is not found."""
        job = ContextIndexingJob(context_id=999)

        mocker.patch(
            "areyouok_telegram.jobs.context_indexing.Context.get_by_ids",
            return_value=[],
        )

        result_context, result_key = await job._fetch_context_and_key()

        assert result_context is None
        assert result_key is None

    async def test_fetch_context_and_key_chat_not_found(self, mocker):
        """Test when chat is not found."""
        context = MagicMock(spec=Context)
        context.id = 123
        context.chat_id = "chat_123"

        job = ContextIndexingJob(context_id=123)

        mocker.patch(
            "areyouok_telegram.jobs.context_indexing.Context.get_by_ids",
            return_value=[context],
        )

        mocker.patch(
            "areyouok_telegram.jobs.context_indexing.Chats.get_by_id",
            return_value=None,
        )

        result_context, result_key = await job._fetch_context_and_key()

        assert result_context == context
        assert result_key is None
