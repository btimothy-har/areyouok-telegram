"""Tests for journaling agent components (unit tests only)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.exceptions import ModelRetry

from areyouok_telegram.data.models import JournalContextMetadata
from areyouok_telegram.llms.chat.agents.journaling import (
    JournalingAgentDependencies,
    complete_journaling_session,
    generate_topics,
    journaling_agent,
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


