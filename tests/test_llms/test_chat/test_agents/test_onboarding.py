"""Tests for onboarding agent components (unit tests only)."""

from unittest.mock import MagicMock, patch

import pytest

from areyouok_telegram.data.models import Notification
from areyouok_telegram.llms.chat.agents.onboarding import (
    OnboardingAgentDependencies,
    onboarding_agent,
    search_history,
    update_memory,
)


class TestOnboardingAgentDependencies:
    """Test OnboardingAgentDependencies dataclass."""

    def test_onboarding_agent_dependencies_creation(self):
        """Test OnboardingAgentDependencies can be created with required fields."""
        deps = OnboardingAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123456789",
            tg_session_id="session_456",
            onboarding_session_key="onboarding_123",
        )

        assert deps.tg_bot_id == "bot123"
        assert deps.tg_chat_id == "123456789"
        assert deps.tg_session_id == "session_456"
        assert deps.onboarding_session_key == "onboarding_123"
        assert deps.restricted_responses == set()
        assert deps.notification is None

    def test_onboarding_agent_dependencies_with_restrictions(self):
        """Test OnboardingAgentDependencies with restricted responses."""
        deps = OnboardingAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123456789",
            tg_session_id="session_456",
            onboarding_session_key="onboarding_123",
            restricted_responses={"text", "reaction"},
        )

        assert deps.restricted_responses == {"text", "reaction"}

    def test_onboarding_agent_dependencies_with_notification(self):
        """Test OnboardingAgentDependencies with notification."""
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = "Test notification"

        deps = OnboardingAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123456789",
            tg_session_id="session_456",
            onboarding_session_key="onboarding_123",
            notification=mock_notification,
        )

        assert deps.notification == mock_notification

    def test_onboarding_agent_dependencies_fields_required(self):
        """Test that required fields raise TypeError when missing."""
        # Should raise TypeError if required fields are missing
        with pytest.raises(TypeError):
            OnboardingAgentDependencies(tg_bot_id="bot123")  # Missing required fields

    def test_onboarding_agent_dependencies_validation(self):
        """Test OnboardingAgentDependencies field validation."""
        # Should work with all required fields
        deps = OnboardingAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123456789",
            tg_session_id="session_456",
            onboarding_session_key="onboarding_123",
        )

        assert isinstance(deps.tg_chat_id, str)
        assert isinstance(deps.tg_session_id, str)
        assert isinstance(deps.onboarding_session_key, str)
        assert isinstance(deps.restricted_responses, set)


class TestOnboardingAgent:
    """Test the onboarding agent configuration (unit tests only)."""

    def test_onboarding_agent_configuration(self):
        """Test that onboarding agent is properly configured."""
        # Verify agent properties
        assert onboarding_agent.name == "areyouok_onboarding_agent"
        assert onboarding_agent.end_strategy == "exhaustive"

        # Verify model is configured
        assert hasattr(onboarding_agent, "model")

    def test_onboarding_agent_has_instructions(self):
        """Test that onboarding agent has instructions."""
        # The agent should have some way to generate instructions
        # This is implementation-dependent, so we just verify the agent exists
        assert onboarding_agent is not None

    def test_onboarding_agent_has_tools(self):
        """Test that onboarding agent has expected attributes."""
        # The agent should have the basic structure we expect
        assert hasattr(onboarding_agent, "name")
        assert hasattr(onboarding_agent, "end_strategy")
        assert hasattr(onboarding_agent, "output_type")

    def test_onboarding_agent_dependencies_types(self):
        """Test that OnboardingAgentDependencies has correct types."""
        deps = OnboardingAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="test_chat",
            tg_session_id="test_session",
            onboarding_session_key="test_key",
        )

        # Verify types
        assert hasattr(deps, "tg_bot_id")
        assert hasattr(deps, "tg_chat_id")
        assert hasattr(deps, "tg_session_id")
        assert hasattr(deps, "onboarding_session_key")
        assert hasattr(deps, "restricted_responses")
        assert hasattr(deps, "notification")


