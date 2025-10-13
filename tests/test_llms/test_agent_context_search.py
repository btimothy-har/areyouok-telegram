"""Tests for context search agent and utilities."""

from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pydantic
import pytest

from areyouok_telegram.llms.context_search import ContextSearchResponse
from areyouok_telegram.llms.context_search import retrieve_relevant_contexts
from areyouok_telegram.llms.context_search import search_chat_context


@pytest.fixture
def mock_context_objects():
    """Create mock Context objects for testing."""
    contexts = []
    for i in range(3):
        context = MagicMock()
        context.id = i + 1
        context.chat_id = "123456"
        context.session_id = f"session_{i}"
        context.type = "session"
        context.created_at = datetime(2025, 1, i + 1, 12, 0, tzinfo=UTC)
        context.content = {
            "life_situation": f"Test life situation {i}",
            "conversation": f"Test conversation {i}",
        }
        context.decrypt_content = MagicMock()
        contexts.append(context)
    return contexts


@pytest.fixture
def mock_nodes():
    """Create mock LlamaIndex nodes for testing."""
    nodes = []
    for i in range(3):
        node = MagicMock()
        node.metadata = {
            "context_id": i + 1,
            "chat_id": "123456",
            "session_id": f"session_{i}",
            "type": "session",
        }
        nodes.append(node)
    return nodes


@pytest.fixture
def mock_chat_object():
    """Create mock Chat object for testing."""
    chat = MagicMock()
    chat.retrieve_key = MagicMock(return_value="test_encryption_key")
    return chat


class TestRetrieveRelevantContexts:
    """Tests for retrieve_relevant_contexts function."""

    @pytest.mark.asyncio
    async def test_successful_retrieval(self, mock_nodes, mock_context_objects, mock_chat_object):
        """Test successful context retrieval with decryption."""
        # Mock the retriever
        mock_retriever = MagicMock()
        mock_retriever.aretrieve = AsyncMock(return_value=mock_nodes)

        with (
            patch("areyouok_telegram.llms.context_search.retriever.context_vector_index") as mock_index,
            patch("areyouok_telegram.llms.context_search.retriever.async_database") as mock_db,
            patch("areyouok_telegram.llms.context_search.retriever.Context") as mock_context_class,
            patch("areyouok_telegram.llms.context_search.retriever.Chats") as mock_chats_class,
        ):
            # Setup mocks
            mock_index.as_retriever.return_value = mock_retriever

            # Mock database context manager
            mock_db_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_db_conn

            # Mock Context.get_by_ids
            mock_context_class.get_by_ids = AsyncMock(return_value=mock_context_objects)

            # Mock Chats.get_by_id
            mock_chats_class.get_by_id = AsyncMock(return_value=mock_chat_object)

            # Execute
            result = await retrieve_relevant_contexts(
                chat_id="123456",
                search_query="test query",
            )

            # Assertions
            assert len(result) == 3
            assert result == mock_context_objects

            # Verify retriever was called with correct filters
            mock_index.as_retriever.assert_called_once()
            call_kwargs = mock_index.as_retriever.call_args[1]
            assert call_kwargs["similarity_top_k"] == 30

            # Verify aretrieve was called
            mock_retriever.aretrieve.assert_called_once_with("test query")

            # Verify Context.get_by_ids was called with correct IDs
            mock_context_class.get_by_ids.assert_called_once()
            call_args = mock_context_class.get_by_ids.call_args
            assert call_args[1]["ids"] == [1, 2, 3]

            # Verify each context was decrypted
            for context in mock_context_objects:
                context.decrypt_content.assert_called_once_with(chat_encryption_key="test_encryption_key")

    @pytest.mark.asyncio
    async def test_no_nodes_found(self):
        """Test when no matching nodes are found."""
        mock_retriever = MagicMock()
        mock_retriever.aretrieve = AsyncMock(return_value=[])

        with patch("areyouok_telegram.llms.context_search.retriever.context_vector_index") as mock_index:
            mock_index.as_retriever.return_value = mock_retriever

            result = await retrieve_relevant_contexts(
                chat_id="123456",
                search_query="test query",
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_no_contexts_in_database(self, mock_nodes, mock_chat_object):
        """Test when nodes are found but contexts don't exist in database."""
        mock_retriever = MagicMock()
        mock_retriever.aretrieve = AsyncMock(return_value=mock_nodes)

        with (
            patch("areyouok_telegram.llms.context_search.retriever.context_vector_index") as mock_index,
            patch("areyouok_telegram.llms.context_search.retriever.async_database") as mock_db,
            patch("areyouok_telegram.llms.context_search.retriever.Context") as mock_context_class,
            patch("areyouok_telegram.llms.context_search.retriever.Chats") as mock_chats_class,
        ):
            mock_index.as_retriever.return_value = mock_retriever

            mock_db_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_db_conn

            # Mock chat retrieval
            mock_chats_class.get_by_id = AsyncMock(return_value=mock_chat_object)

            # No contexts found in database
            mock_context_class.get_by_ids = AsyncMock(return_value=[])

            result = await retrieve_relevant_contexts(
                chat_id="123456",
                search_query="test query",
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_chat_not_found(self, mock_nodes, mock_context_objects):
        """Test when chat object is not found - should raise AttributeError."""
        mock_retriever = MagicMock()
        mock_retriever.aretrieve = AsyncMock(return_value=mock_nodes)

        with (
            patch("areyouok_telegram.llms.context_search.retriever.context_vector_index") as mock_index,
            patch("areyouok_telegram.llms.context_search.retriever.async_database") as mock_db,
            patch("areyouok_telegram.llms.context_search.retriever.Context") as mock_context_class,
            patch("areyouok_telegram.llms.context_search.retriever.Chats") as mock_chats_class,
        ):
            mock_index.as_retriever.return_value = mock_retriever

            mock_db_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_db_conn

            mock_context_class.get_by_ids = AsyncMock(return_value=mock_context_objects)
            mock_chats_class.get_by_id = AsyncMock(return_value=None)

            # Should raise AttributeError when trying to call retrieve_key on None
            with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'retrieve_key'"):
                await retrieve_relevant_contexts(
                    chat_id="123456",
                    search_query="test query",
                )

    @pytest.mark.asyncio
    async def test_retrieval_uses_config_limit(self, mock_nodes, mock_context_objects, mock_chat_object):
        """Test retrieval uses RAG_TOP_K from config."""
        mock_retriever = MagicMock()
        mock_retriever.aretrieve = AsyncMock(return_value=mock_nodes)

        with (
            patch("areyouok_telegram.llms.context_search.retriever.context_vector_index") as mock_index,
            patch("areyouok_telegram.llms.context_search.retriever.async_database") as mock_db,
            patch("areyouok_telegram.llms.context_search.retriever.Context") as mock_context_class,
            patch("areyouok_telegram.llms.context_search.retriever.Chats") as mock_chats_class,
            patch("areyouok_telegram.llms.context_search.retriever.RAG_TOP_K", 30),
        ):
            mock_index.as_retriever.return_value = mock_retriever

            mock_db_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_db_conn

            mock_context_class.get_by_ids = AsyncMock(return_value=mock_context_objects)
            mock_chats_class.get_by_id = AsyncMock(return_value=mock_chat_object)

            result = await retrieve_relevant_contexts(
                chat_id="123456",
                search_query="test query",
            )

            # Verify config limit of 30 was used
            call_kwargs = mock_index.as_retriever.call_args[1]
            assert call_kwargs["similarity_top_k"] == 30
            assert len(result) == 3


class TestSearchPastConversations:
    """Tests for search_past_conversations function."""

    @pytest.mark.asyncio
    async def test_successful_search_with_results(self, mock_context_objects):
        """Test successful search that returns formatted results."""
        mock_agent_output = ContextSearchResponse(
            answer="The user felt anxious about work deadlines on multiple occasions.",
            summary="User expressed anxiety about work in 3 conversations, mentioning tight deadlines and pressure.",
        )

        mock_agent_result = MagicMock()
        mock_agent_result.output = mock_agent_output

        with (
            patch("areyouok_telegram.llms.context_search.search.retrieve_relevant_contexts") as mock_retrieve,
            patch("areyouok_telegram.llms.context_search.search.run_agent_with_tracking") as mock_run_agent,
        ):
            mock_retrieve.return_value = mock_context_objects
            mock_run_agent.return_value = mock_agent_result

            result = await search_chat_context(
                chat_id="123456",
                session_id="session_123",
                search_query="times user felt anxious",
            )

            # Verify retrieve was called
            mock_retrieve.assert_called_once_with(
                chat_id="123456",
                search_query="times user felt anxious",
            )

            # Verify agent was called
            mock_run_agent.assert_called_once()
            agent_call_args = mock_run_agent.call_args
            assert agent_call_args[1]["chat_id"] == "123456"
            assert agent_call_args[1]["session_id"] == "session_123"

            # Verify output format
            assert "**Answer:**" in result
            assert "**Summary of Retrieved Contexts:**" in result
            assert "Retrieved 3 relevant conversation(s)" in result
            assert mock_agent_output.answer in result
            assert mock_agent_output.summary in result

    @pytest.mark.asyncio
    async def test_search_with_no_results(self):
        """Test search when no contexts are found."""
        with patch("areyouok_telegram.llms.context_search.search.retrieve_relevant_contexts") as mock_retrieve:
            mock_retrieve.return_value = []

            result = await search_chat_context(
                chat_id="123456",
                session_id="session_123",
                search_query="nonexistent topic",
            )

            assert "No relevant past conversations found" in result
            assert "nonexistent topic" in result

    @pytest.mark.asyncio
    async def test_search_with_retrieval_exception(self):
        """Test error handling when retrieval fails."""
        with patch("areyouok_telegram.llms.context_search.search.retrieve_relevant_contexts") as mock_retrieve:
            mock_retrieve.side_effect = Exception("Database connection failed")

            result = await search_chat_context(
                chat_id="123456",
                session_id="session_123",
                search_query="test query",
            )

            assert "Error searching past conversations" in result
            assert "Database connection failed" in result

    @pytest.mark.asyncio
    async def test_search_with_agent_exception(self, mock_context_objects):
        """Test error handling when agent fails."""
        with (
            patch("areyouok_telegram.llms.context_search.search.retrieve_relevant_contexts") as mock_retrieve,
            patch("areyouok_telegram.llms.context_search.search.run_agent_with_tracking") as mock_run_agent,
        ):
            mock_retrieve.return_value = mock_context_objects
            mock_run_agent.side_effect = Exception("Agent execution failed")

            result = await search_chat_context(
                chat_id="123456",
                session_id="session_123",
                search_query="test query",
            )

            assert "Error searching past conversations" in result
            assert "Agent execution failed" in result

    @pytest.mark.asyncio
    async def test_search_formats_contexts_correctly(self, mock_context_objects):
        """Test that contexts are formatted with relative timestamps correctly."""
        mock_agent_output = ContextSearchResponse(
            answer="Test answer",
            summary="Test summary",
        )

        mock_agent_result = MagicMock()
        mock_agent_result.output = mock_agent_output

        with (
            patch("areyouok_telegram.llms.context_search.search.retrieve_relevant_contexts") as mock_retrieve,
            patch("areyouok_telegram.llms.context_search.search.run_agent_with_tracking") as mock_run_agent,
            patch("areyouok_telegram.llms.context_search.search.format_relative_time") as mock_time_format,
        ):
            mock_retrieve.return_value = mock_context_objects
            mock_run_agent.return_value = mock_agent_result
            mock_time_format.side_effect = lambda dt: f"{(datetime(2025, 1, 10, tzinfo=UTC) - dt).days} days ago"

            await search_chat_context(
                chat_id="123456",
                session_id="session_123",
                search_query="test query",
            )

            # Check the prompt passed to the agent
            agent_call_args = mock_run_agent.call_args
            prompt = agent_call_args[1]["run_kwargs"]["user_prompt"]

            # Verify formatted contexts include relative timestamps
            assert "Context 1 [8 days ago]:" in prompt
            assert "Context 2 [7 days ago]:" in prompt
            assert "Context 3 [6 days ago]:" in prompt

            # Verify content is formatted
            assert "Test life situation 0" in prompt
            assert "Test conversation 0" in prompt


class TestContextSearchResponse:
    """Tests for ContextSearchResponse model."""

    def test_model_creation(self):
        """Test that the model can be created with valid data."""
        response = ContextSearchResponse(
            answer="This is an answer",
            summary="This is a summary",
        )

        assert response.answer == "This is an answer"
        assert response.summary == "This is a summary"

    def test_model_validation(self):
        """Test that the model validates required fields."""
        with pytest.raises(pydantic.ValidationError):
            ContextSearchResponse(answer="Only answer")
