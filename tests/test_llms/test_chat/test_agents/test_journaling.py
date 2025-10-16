"""Tests for journaling agent components (unit tests only)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.exceptions import ModelRetry

from areyouok_telegram.data import JournalContextMetadata
from areyouok_telegram.llms.chat.agents.journaling import (
    JournalingAgentDependencies,
    complete_journaling_session,
    generate_topics,
    journaling_agent,
    retrieve_journal_context,
    update_selected_topic,
)
from areyouok_telegram.llms.exceptions import JournalingError


class TestJournalingAgentDependencies:
    """Test JournalingAgentDependencies dataclass."""

    def test_journaling_agent_dependencies_creation(self):
        """Test JournalingAgentDependencies can be created with required fields."""
        metadata = JournalContextMetadata(
            phase="topic_selection",
            generated_topics=[],
            selected_topic=None,
        )

        deps = JournalingAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123456789",
            tg_session_id="session_456",
            journaling_session_key="journaling_123",
            journaling_session_metadata=metadata,
        )

        assert deps.tg_bot_id == "bot123"
        assert deps.tg_chat_id == "123456789"
        assert deps.tg_session_id == "session_456"
        assert deps.journaling_session_key == "journaling_123"
        assert deps.journaling_session_metadata == metadata
        assert deps.restricted_responses == set()

    def test_journaling_agent_dependencies_with_restrictions(self):
        """Test JournalingAgentDependencies with restricted responses."""
        metadata = JournalContextMetadata(
            phase="topic_selection",
            generated_topics=[],
            selected_topic=None,
        )

        deps = JournalingAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123456789",
            tg_session_id="session_456",
            journaling_session_key="journaling_123",
            journaling_session_metadata=metadata,
            restricted_responses={"text", "reaction"},
        )

        assert deps.restricted_responses == {"text", "reaction"}

    def test_journaling_agent_dependencies_to_dict(self):
        """Test to_dict method."""
        metadata = JournalContextMetadata(
            phase="topic_selection",
            generated_topics=[],
            selected_topic=None,
        )

        deps = JournalingAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123456789",
            tg_session_id="session_456",
            journaling_session_key="journaling_123",
            journaling_session_metadata=metadata,
            restricted_responses={"text"},
        )

        result = deps.to_dict()

        assert result["tg_bot_id"] == "bot123"
        assert result["tg_chat_id"] == "123456789"
        assert result["tg_session_id"] == "session_456"
        assert result["journaling_session_key"] == "journaling_123"
        assert result["restricted_responses"] == ["text"]
        assert result["journaling_session_metadata"] == metadata.model_dump()

    def test_journaling_agent_dependencies_fields_required(self):
        """Test that required fields raise TypeError when missing."""
        with pytest.raises(TypeError):
            JournalingAgentDependencies(tg_bot_id="bot123")  # Missing required fields


class TestJournalingAgent:
    """Test the journaling agent configuration (unit tests only)."""

    def test_journaling_agent_configuration(self):
        """Test that journaling agent is properly configured."""
        assert journaling_agent.name == "areyouok_journaling_agent"
        assert journaling_agent.end_strategy == "exhaustive"
        assert hasattr(journaling_agent, "model")

    def test_journaling_agent_has_correct_deps_type(self):
        """Test that journaling agent has correct dependency type."""
        # The agent should be configured with JournalingAgentDependencies
        assert journaling_agent.deps_type == JournalingAgentDependencies


class TestGenerateTopicsTool:
    """Test generate_topics tool."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock context for agent tools."""
        mock_ctx = MagicMock()
        metadata = JournalContextMetadata(
            phase="topic_selection",
            generated_topics=[],
            selected_topic=None,
        )
        mock_deps = JournalingAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123456789",
            tg_session_id="session_456",
            journaling_session_key="journaling_123",
            journaling_session_metadata=metadata,
        )
        mock_ctx.deps = mock_deps
        return mock_ctx

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.journaling.data_operations.get_chat_encryption_key")
    @patch("areyouok_telegram.llms.chat.agents.journaling.retrieve_journal_context")
    @patch("areyouok_telegram.llms.chat.agents.journaling.run_agent_with_tracking")
    @patch("areyouok_telegram.llms.chat.agents.journaling.async_database")
    @patch("areyouok_telegram.llms.chat.agents.journaling.GuidedSessions.get_by_guided_session_key")
    @patch("areyouok_telegram.llms.chat.agents.journaling.Chats.get_by_id")
    async def test_generate_topics_with_context(
        self,
        mock_chats_get,
        mock_sessions_get,
        mock_async_database,
        mock_run_agent,
        mock_retrieve_context,
        mock_get_encryption_key,
        mock_context,
    ):
        """Test generate_topics with available context."""
        # Setup mocks
        mock_get_encryption_key.return_value = "test_key"

        mock_context_item = MagicMock()
        mock_context_item.decrypt_content = MagicMock()
        mock_context_item.created_at = datetime.now(UTC)
        mock_context_item.type = "session"
        mock_context_item.content = "Test content"
        mock_retrieve_context.return_value = [mock_context_item]

        mock_agent_result = MagicMock()
        mock_agent_result.output = MagicMock()
        mock_agent_result.output.prompts = ["Prompt 1", "Prompt 2", "Prompt 3"]
        mock_run_agent.return_value = mock_agent_result

        mock_session = MagicMock()
        mock_session.update_metadata = AsyncMock()
        mock_sessions_get.return_value = mock_session

        mock_chat = MagicMock()
        mock_chat.retrieve_key = MagicMock(return_value="test_key")
        mock_chats_get.return_value = mock_chat

        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__.return_value = mock_db_conn

        # Execute
        result = await generate_topics(ctx=mock_context)

        # Verify
        assert result == "Prompt 1\nPrompt 2\nPrompt 3"
        mock_session.update_metadata.assert_called_once()
        assert mock_context.deps.journaling_session_metadata.generated_topics == ["Prompt 1", "Prompt 2", "Prompt 3"]

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.journaling.data_operations.get_chat_encryption_key")
    @patch("areyouok_telegram.llms.chat.agents.journaling.retrieve_journal_context")
    async def test_generate_topics_without_context(
        self,
        mock_retrieve_context,
        mock_get_encryption_key,
        mock_context,
    ):
        """Test generate_topics when no context is available."""
        # Setup mocks
        mock_get_encryption_key.return_value = "test_key"
        mock_retrieve_context.return_value = None

        # Execute
        result = await generate_topics(ctx=mock_context)

        # Verify - should return instruction for agent to generate generic prompts
        assert "No recent context available" in result
        assert "generic" in result.lower()


class TestUpdateSelectedTopicTool:
    """Test update_selected_topic tool."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock context."""
        mock_ctx = MagicMock()
        metadata = JournalContextMetadata(
            phase="topic_selection",
            generated_topics=["Topic 1", "Topic 2", "Topic 3"],
            selected_topic=None,
        )
        mock_deps = JournalingAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123456789",
            tg_session_id="session_456",
            journaling_session_key="journaling_123",
            journaling_session_metadata=metadata,
        )
        mock_ctx.deps = mock_deps
        return mock_ctx

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.journaling.async_database")
    @patch("areyouok_telegram.llms.chat.agents.journaling.GuidedSessions.get_by_guided_session_key")
    @patch("areyouok_telegram.llms.chat.agents.journaling.Chats.get_by_id")
    async def test_update_selected_topic_success(
        self,
        mock_chats_get,
        mock_sessions_get,
        mock_async_database,
        mock_context,
    ):
        """Test successful topic selection."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session.update_metadata = AsyncMock()
        mock_sessions_get.return_value = mock_session

        mock_chat = MagicMock()
        mock_chat.retrieve_key = MagicMock(return_value="test_key")
        mock_chats_get.return_value = mock_chat

        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__.return_value = mock_db_conn

        # Execute
        result = await update_selected_topic(ctx=mock_context, topic="Topic 1")

        # Verify
        assert "updated successfully" in result.lower()
        assert mock_context.deps.journaling_session_metadata.phase == "journaling"
        assert mock_context.deps.journaling_session_metadata.selected_topic == "Topic 1"
        mock_session.update_metadata.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_selected_topic_wrong_phase(self, mock_context):
        """Test that updating topic fails when not in topic_selection phase."""
        # Set phase to something other than topic_selection
        mock_context.deps.journaling_session_metadata.phase = "journaling"

        # Execute and verify it raises
        with pytest.raises(ModelRetry, match="not in the topic_selection phase"):
            await update_selected_topic(ctx=mock_context, topic="Topic 1")


class TestCompleteJournalingSessionTool:
    """Test complete_journaling_session tool."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock context."""
        mock_ctx = MagicMock()
        metadata = JournalContextMetadata(
            phase="journaling",
            generated_topics=["Topic 1", "Topic 2", "Topic 3"],
            selected_topic="Topic 1",
        )
        mock_deps = JournalingAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123456789",
            tg_session_id="session_456",
            journaling_session_key="journaling_123",
            journaling_session_metadata=metadata,
        )
        mock_ctx.deps = mock_deps
        return mock_ctx

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.journaling.async_database")
    @patch("areyouok_telegram.llms.chat.agents.journaling.GuidedSessions.get_by_guided_session_key")
    @patch("areyouok_telegram.llms.chat.agents.journaling.Chats.get_by_id")
    async def test_complete_journaling_session_success(
        self,
        mock_chats_get,
        mock_sessions_get,
        mock_async_database,
        mock_context,
    ):
        """Test successful session completion."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session.is_active = True
        mock_session.update_metadata = AsyncMock()
        mock_session.complete = AsyncMock()
        mock_sessions_get.return_value = mock_session

        mock_chat = MagicMock()
        mock_chat.retrieve_key = MagicMock(return_value="test_key")
        mock_chats_get.return_value = mock_chat

        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__.return_value = mock_db_conn

        # Execute
        result = await complete_journaling_session(ctx=mock_context)

        # Verify
        assert "completed successfully" in result.lower()
        assert mock_context.deps.journaling_session_metadata.phase == "complete"
        mock_session.complete.assert_called_once()
        mock_session.update_metadata.assert_called_once()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.journaling.async_database")
    @patch("areyouok_telegram.llms.chat.agents.journaling.GuidedSessions.get_by_guided_session_key")
    async def test_complete_journaling_session_not_active(
        self,
        mock_sessions_get,
        mock_async_database,
        mock_context,
    ):
        """Test session completion fails when session is not active."""
        # Create mock inactive session
        mock_session = MagicMock()
        mock_session.is_active = False
        mock_session.state = "complete"
        mock_sessions_get.return_value = mock_session

        # Mock database
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__.return_value = mock_db_conn

        # Execute and verify it raises
        with pytest.raises(JournalingError, match="currently complete"):
            await complete_journaling_session(ctx=mock_context)


class TestRetrieveJournalContext:
    """Test retrieve_journal_context function."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.journaling.async_database")
    @patch("areyouok_telegram.llms.chat.agents.journaling.GuidedSessions.get_by_chat_id")
    @patch("areyouok_telegram.llms.chat.agents.journaling.Context.get_by_chat_id")
    async def test_retrieve_journal_context_with_previous_session(
        self,
        mock_context_get,
        mock_sessions_get,
        mock_async_database,
    ):
        """Test retrieving context when there's a previous journal session."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__.return_value = mock_db_conn

        # Mock previous journal session
        mock_prev_session = MagicMock()
        mock_prev_session.completed_at = datetime.now(UTC) - timedelta(days=2)
        mock_sessions_get.return_value = [mock_prev_session]

        # Mock contexts
        mock_context1 = MagicMock()
        mock_context1.type = "session"
        mock_context2 = MagicMock()
        mock_context2.type = "memory"
        mock_context_get.return_value = [mock_context1, mock_context2]

        # Execute
        result = await retrieve_journal_context(chat_id="123456789")

        # Verify
        assert result is not None
        assert len(result) == 2
        mock_context_get.assert_called_once()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.journaling.async_database")
    @patch("areyouok_telegram.llms.chat.agents.journaling.GuidedSessions.get_by_chat_id")
    @patch("areyouok_telegram.llms.chat.agents.journaling.Context.get_by_chat_id")
    async def test_retrieve_journal_context_no_contexts(
        self,
        mock_context_get,
        mock_sessions_get,
        mock_async_database,
    ):
        """Test retrieving context when there are no contexts available."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__.return_value = mock_db_conn

        mock_sessions_get.return_value = []
        mock_context_get.return_value = []

        # Execute
        result = await retrieve_journal_context(chat_id="123456789")

        # Verify
        assert result is None
