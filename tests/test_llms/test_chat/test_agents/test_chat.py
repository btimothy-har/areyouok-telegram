"""Tests for chat agents."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from areyouok_telegram.data.models import Notification, UserMetadata
from areyouok_telegram.llms.agent_anonymizer import anonymization_agent
from areyouok_telegram.llms.chat.agents.chat import (
    ChatAgentDependencies,
    get_current_time,
    instructions_with_personality_switch,
    search_history,
    update_communication_style,
    update_memory,
)
from areyouok_telegram.llms.chat.personalities import PersonalityTypes
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError


class TestChatAgentDependencies:
    """Test ChatAgentDependencies dataclass."""

    def test_dependencies_creation_with_defaults(self):
        """Test ChatAgentDependencies creation with default values."""
        tg_chat_id = "123456"
        tg_session_id = "session_123"

        deps = ChatAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id=tg_chat_id,
            tg_session_id=tg_session_id,
        )

        assert deps.tg_bot_id == "bot123"
        assert deps.tg_chat_id == tg_chat_id
        assert deps.tg_session_id == tg_session_id
        assert deps.personality == PersonalityTypes.COMPANIONSHIP.value
        assert deps.restricted_responses == set()
        assert deps.notification is None

    def test_dependencies_creation_with_custom_values(self):
        """Test ChatAgentDependencies creation with custom values."""
        tg_chat_id = "123456"
        tg_session_id = "session_123"
        personality = PersonalityTypes.ANCHORING.value
        restricted_responses = {"text", "reaction"}
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = "Special instruction"

        deps = ChatAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id=tg_chat_id,
            tg_session_id=tg_session_id,
            personality=personality,
            restricted_responses=restricted_responses,
            notification=mock_notification,
        )

        assert deps.personality == personality
        assert deps.restricted_responses == restricted_responses
        assert deps.notification == mock_notification


class TestInstructionsWithPersonalitySwitch:
    """Test instructions_with_personality_switch function."""

    @pytest.fixture
    def mock_user_metadata(self):
        """Create mock user metadata."""
        metadata = MagicMock(spec=UserMetadata)
        metadata.preferred_name = "Alice"
        metadata.country = "USA"
        metadata.timezone = "America/New_York"
        metadata.communication_style = "casual and friendly"
        return metadata

    @pytest.fixture
    def mock_run_context(self):
        """Create mock pydantic_ai run context."""
        context = MagicMock()
        context.deps = MagicMock(spec=ChatAgentDependencies)
        context.deps.tg_chat_id = "123456"
        context.deps.personality = PersonalityTypes.EXPLORATION.value
        context.deps.restricted_responses = set()
        context.deps.instruction = None
        return context

    @pytest.mark.asyncio
    async def test_instructions_with_default_settings(self, mock_run_context, mock_user_metadata):  # noqa: ARG002
        """Test instructions generation with default settings."""
        with patch.object(UserMetadata, "get_by_user_id", new=AsyncMock(return_value=mock_user_metadata)):
            result = await instructions_with_personality_switch(mock_run_context)

            assert isinstance(result, str)

            # Verify user preferences are included
            assert "<user_preferences>" in result
            assert "Alice" in result
            assert "America/New_York" in result
            assert "casual and friendly" in result

    @pytest.mark.asyncio
    async def test_instructions_with_restricted_text_response(self, mock_run_context, mock_user_metadata):
        """Test instructions generation with restricted text responses."""
        mock_run_context.deps.restricted_responses = {"text"}

        with patch.object(UserMetadata, "get_by_user_id", new=AsyncMock(return_value=mock_user_metadata)):
            result = await instructions_with_personality_switch(mock_run_context)

            assert "recently responded via a text response" in result
            assert "cannot do so again immediately" in result

    @pytest.mark.asyncio
    async def test_instructions_with_restricted_personality_switch(self, mock_run_context, mock_user_metadata):
        """Test instructions generation with restricted personality switches."""
        mock_run_context.deps.restricted_responses = {"switch_personality"}

        with patch.object(UserMetadata, "get_by_user_id", new=AsyncMock(return_value=mock_user_metadata)):
            result = await instructions_with_personality_switch(mock_run_context)

            assert "will not be allowed to switch personalities" in result

    @pytest.mark.asyncio
    async def test_instructions_with_multiple_restrictions(self, mock_run_context, mock_user_metadata):
        """Test instructions generation with multiple restrictions."""
        mock_run_context.deps.restricted_responses = {"text", "switch_personality"}

        with patch.object(UserMetadata, "get_by_user_id", new=AsyncMock(return_value=mock_user_metadata)):
            result = await instructions_with_personality_switch(mock_run_context)

            assert "recently responded via a text response" in result
            assert "will not be allowed to switch personalities" in result

    @pytest.mark.asyncio
    async def test_instructions_with_custom_instruction(self, mock_run_context, mock_user_metadata):
        """Test instructions generation with custom notification message."""
        notification_message = "Please acknowledge this important message"
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = notification_message
        mock_run_context.deps.notification = mock_notification

        with patch.object(UserMetadata, "get_by_user_id", new=AsyncMock(return_value=mock_user_metadata)):
            result = await instructions_with_personality_switch(mock_run_context)

            assert notification_message in result
            assert "<message>" in result

    @pytest.mark.asyncio
    async def test_instructions_with_different_personality(self, mock_run_context, mock_user_metadata):
        """Test instructions generation with different personality."""
        mock_run_context.deps.personality = PersonalityTypes.ANCHORING.value

        with patch.object(UserMetadata, "get_by_user_id", new=AsyncMock(return_value=mock_user_metadata)):
            result = await instructions_with_personality_switch(mock_run_context)

            # Should contain anchoring personality characteristics
            assert "Grounding presence" in result or "emotional stability" in result

    @pytest.mark.asyncio
    async def test_instructions_user_metadata_called_correctly(self, mock_run_context):
        """Test that UserMetadata.get_by_user_id is called with correct chat_id."""
        mock_metadata = MagicMock(spec=UserMetadata)
        mock_metadata.preferred_name = "Test"
        mock_metadata.country = "Test"
        mock_metadata.timezone = "UTC"
        mock_metadata.communication_style = "Test"

        with patch.object(UserMetadata, "get_by_user_id", new=AsyncMock(return_value=mock_metadata)) as mock_get_user:
            await instructions_with_personality_switch(mock_run_context)

            mock_get_user.assert_called_once_with(ANY, user_id=mock_run_context.deps.tg_chat_id)


