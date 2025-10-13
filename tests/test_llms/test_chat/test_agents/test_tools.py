"""Tests for shared chat agent tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from areyouok_telegram.llms.chat.agents.tools import search_history_impl, update_memory_impl
from areyouok_telegram.llms.exceptions import ContextSearchError, MemoryUpdateError


class MockDependencies:
    """Mock dependencies matching ChatDependencies protocol."""

    def __init__(self, chat_id: str, session_id: str):
        self.tg_chat_id = chat_id
        self.tg_session_id = session_id


class TestUpdateMemoryImpl:
    """Test update_memory_impl shared tool."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.tools.async_database")
    @patch("areyouok_telegram.llms.chat.agents.tools.Chats")
    @patch("areyouok_telegram.llms.chat.agents.tools.Context")
    async def test_update_memory_success(self, mock_context, mock_chats, _mock_db):
        """Test successful memory update."""
        deps = MockDependencies("chat123", "session456")
        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "fake_key"
        mock_chats.get_by_id = AsyncMock(return_value=mock_chat)
        mock_context.new = AsyncMock()

        result = await update_memory_impl(deps, "User loves hiking")

        assert "Information committed to memory" in result
        assert "User loves hiking" in result
        mock_context.new.assert_called_once()
        call_kwargs = mock_context.new.call_args[1]
        assert call_kwargs["ctype"] == "memory"
        assert call_kwargs["content"] == "User loves hiking"
        assert call_kwargs["chat_id"] == "chat123"
        assert call_kwargs["session_id"] == "session456"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.tools.async_database")
    @patch("areyouok_telegram.llms.chat.agents.tools.Chats")
    async def test_update_memory_error(self, mock_chats, _mock_db):
        """Test memory update with database error."""
        deps = MockDependencies("chat123", "session456")
        mock_chats.get_by_id = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(MemoryUpdateError) as exc_info:
            await update_memory_impl(deps, "Test memory")

        assert exc_info.value.memory_info == "Test memory"
        assert "DB error" in str(exc_info.value.exception)

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.tools.async_database")
    @patch("areyouok_telegram.llms.chat.agents.tools.Chats")
    @patch("areyouok_telegram.llms.chat.agents.tools.Context")
    async def test_update_memory_encryption_key_retrieval(self, mock_context, mock_chats, _mock_db):
        """Test that encryption key is properly retrieved and used."""
        deps = MockDependencies("chat123", "session456")
        mock_chat = MagicMock()
        test_key = "test_encryption_key_12345"
        mock_chat.retrieve_key.return_value = test_key
        mock_chats.get_by_id = AsyncMock(return_value=mock_chat)
        mock_context.new = AsyncMock()

        await update_memory_impl(deps, "User prefers tea over coffee")

        mock_chat.retrieve_key.assert_called_once()
        call_kwargs = mock_context.new.call_args[1]
        assert call_kwargs["chat_encryption_key"] == test_key

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.tools.async_database")
    @patch("areyouok_telegram.llms.chat.agents.tools.Chats")
    @patch("areyouok_telegram.llms.chat.agents.tools.Context")
    async def test_update_memory_context_creation_error(self, mock_context, mock_chats, _mock_db):
        """Test memory update when context creation fails."""
        deps = MockDependencies("chat123", "session456")
        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "fake_key"
        mock_chats.get_by_id = AsyncMock(return_value=mock_chat)
        mock_context.new = AsyncMock(side_effect=ValueError("Invalid context"))

        with pytest.raises(MemoryUpdateError) as exc_info:
            await update_memory_impl(deps, "Memory content")

        assert exc_info.value.memory_info == "Memory content"
        assert isinstance(exc_info.value.exception, ValueError)


class TestSearchHistoryImpl:
    """Test search_history_impl shared tool."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.tools.search_chat_context")
    async def test_search_history_success(self, mock_search):
        """Test successful history search."""
        deps = MockDependencies("chat123", "session456")
        mock_search.return_value = "Found 3 relevant memories"

        result = await search_history_impl(deps, "times user felt anxious")

        assert result == "Found 3 relevant memories"
        mock_search.assert_called_once_with(
            chat_id="chat123", session_id="session456", search_query="times user felt anxious"
        )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.tools.search_chat_context")
    async def test_search_history_error(self, mock_search):
        """Test search history with error."""
        deps = MockDependencies("chat123", "session456")
        mock_search.side_effect = RuntimeError("Search failed")

        with pytest.raises(ContextSearchError) as exc_info:
            await search_history_impl(deps, "test query")

        assert exc_info.value.search_query == "test query"
        assert isinstance(exc_info.value.exception, RuntimeError)

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.tools.search_chat_context")
    async def test_search_history_with_complex_query(self, mock_search):
        """Test search with complex multi-word query."""
        deps = MockDependencies("chat789", "session999")
        mock_search.return_value = "**Answer:** User expressed anxiety about upcoming presentations"

        result = await search_history_impl(deps, "when did user feel anxious about work presentations")

        assert "User expressed anxiety" in result
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args[1]
        assert call_kwargs["search_query"] == "when did user feel anxious about work presentations"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.tools.search_chat_context")
    async def test_search_history_no_results(self, mock_search):
        """Test search history when no results found."""
        deps = MockDependencies("chat123", "session456")
        mock_search.return_value = "No relevant past conversations found"

        result = await search_history_impl(deps, "nonexistent topic")

        assert result == "No relevant past conversations found"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.tools.search_chat_context")
    async def test_search_history_connection_error(self, mock_search):
        """Test search history with connection error."""
        deps = MockDependencies("chat123", "session456")
        mock_search.side_effect = ConnectionError("Vector store unreachable")

        with pytest.raises(ContextSearchError) as exc_info:
            await search_history_impl(deps, "search query")

        assert exc_info.value.search_query == "search query"
        assert "Vector store unreachable" in str(exc_info.value.exception)


class TestDependenciesProtocol:
    """Test that MockDependencies matches the protocol."""

    def test_mock_dependencies_has_required_attributes(self):
        """Test that MockDependencies has all required protocol attributes."""
        deps = MockDependencies("test_chat", "test_session")

        assert hasattr(deps, "tg_chat_id")
        assert hasattr(deps, "tg_session_id")
        assert deps.tg_chat_id == "test_chat"
        assert deps.tg_session_id == "test_session"
