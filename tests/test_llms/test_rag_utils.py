"""Tests for RAG utility functions."""

from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from areyouok_telegram.data import Context
from areyouok_telegram.llms.rag.utils import create_context_document
from areyouok_telegram.llms.rag.utils import fetch_contexts_by_ids


@pytest.fixture
def chat_encryption_key() -> str:
    """Return a test encryption key."""
    return "test_key_12345678901234567890123456789012"


@pytest.fixture
def mock_context():
    """Create a mock Context object."""
    context = MagicMock(spec=Context)
    context.id = 123
    context.context_key = "test_key"
    context.chat_id = "chat_123"
    context.session_id = "session_456"
    context.type = "response"
    context.created_at = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
    return context


class TestCreateContextDocument:
    """Tests for create_context_document function."""

    @freeze_time("2025-01-15 12:00:00")
    async def test_creates_document_with_correct_metadata(self, mock_context):
        """Test that Document is created with correct metadata."""
        context = mock_context

        decrypted_content = "This is test content"

        document = create_context_document(context, decrypted_content)

        assert document.text == decrypted_content
        assert document.id_ == "123"
        assert document.metadata["context_id"] == 123
        assert document.metadata["context_key"] == "test_key"
        assert document.metadata["chat_id"] == "chat_123"
        assert document.metadata["session_id"] == "session_456"
        assert document.metadata["type"] == "response"
        assert "created_at" in document.metadata

    async def test_handles_empty_content(self):
        """Test that empty content is handled correctly."""
        context = MagicMock(spec=Context)
        context.id = 456
        context.context_key = "key"
        context.chat_id = "chat"
        context.session_id = "session"
        context.type = "response"
        context.created_at = datetime(2025, 1, 15, tzinfo=UTC)

        decrypted_content = ""

        document = create_context_document(context, decrypted_content)

        assert document.text == ""
        assert document.metadata["context_id"] == 456


class TestFetchContextsByIds:
    """Tests for fetch_contexts_by_ids function."""

    async def test_fetches_and_decrypts_contexts(
        self,
        mocker,
        chat_encryption_key,
    ):
        """Test that contexts are fetched and decrypted."""
        # Mock the database call
        mock_ctx1 = MagicMock(spec=Context)
        mock_ctx1.id = 1
        mock_ctx1.decrypt_content = MagicMock(return_value="decrypted")

        mock_ctx2 = MagicMock(spec=Context)
        mock_ctx2.id = 2
        mock_ctx2.decrypt_content = MagicMock(return_value="decrypted")

        mock_contexts = [mock_ctx1, mock_ctx2]

        mocker.patch(
            "areyouok_telegram.llms.rag.utils.Context.get_by_ids",
            return_value=mock_contexts,
        )

        result = await fetch_contexts_by_ids([1, 2], chat_encryption_key)

        assert len(result) == 2
        assert result[0].id == 1
        assert result[1].id == 2

        # Verify decrypt was called on each context
        mock_ctx1.decrypt_content.assert_called_once_with(
            chat_encryption_key=chat_encryption_key,
        )
        mock_ctx2.decrypt_content.assert_called_once_with(
            chat_encryption_key=chat_encryption_key,
        )

    async def test_handles_empty_id_list(self, chat_encryption_key):
        """Test that empty ID list returns empty list."""
        result = await fetch_contexts_by_ids([], chat_encryption_key)

        assert result == []

    async def test_handles_no_contexts_found(self, mocker, chat_encryption_key):
        """Test that no contexts found returns empty list."""
        mocker.patch(
            "areyouok_telegram.llms.rag.utils.Context.get_by_ids",
            return_value=[],
        )

        result = await fetch_contexts_by_ids([999], chat_encryption_key)

        assert result == []
