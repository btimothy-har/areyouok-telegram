"""Tests for chat agents."""

from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from telegram.ext import ContextTypes

from areyouok_telegram.data.models.user_metadata import UserMetadata
from areyouok_telegram.llms.chat.agents.chat import ChatAgentDependencies
from areyouok_telegram.llms.chat.agents.chat import instructions_with_personality_switch
from areyouok_telegram.llms.chat.agents.chat import update_communication_style
from areyouok_telegram.llms.chat.constants import USER_PREFERENCES
from areyouok_telegram.llms.chat.personalities import PersonalityTypes
from areyouok_telegram.llms.chat.prompt import BaseChatPromptTemplate
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError
from areyouok_telegram.llms.validators.anonymizer import anonymization_agent


class TestChatAgentDependencies:
    """Test ChatAgentDependencies dataclass."""

    def test_dependencies_creation_with_defaults(self):
        """Test ChatAgentDependencies creation with default values."""
        tg_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        tg_chat_id = "123456"
        tg_session_id = "session_123"

        deps = ChatAgentDependencies(
            tg_context=tg_context,
            tg_chat_id=tg_chat_id,
            tg_session_id=tg_session_id,
        )

        assert deps.tg_context == tg_context
        assert deps.tg_chat_id == tg_chat_id
        assert deps.tg_session_id == tg_session_id
        assert deps.personality == PersonalityTypes.EXPLORATION.value
        assert deps.restricted_responses == set()
        assert deps.instruction is None

    def test_dependencies_creation_with_custom_values(self):
        """Test ChatAgentDependencies creation with custom values."""
        tg_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        tg_chat_id = "123456"
        tg_session_id = "session_123"
        personality = PersonalityTypes.ANCHORING.value
        restricted_responses = {"text", "reaction"}
        instruction = "Special instruction"

        deps = ChatAgentDependencies(
            tg_context=tg_context,
            tg_chat_id=tg_chat_id,
            tg_session_id=tg_session_id,
            personality=personality,
            restricted_responses=restricted_responses,
            instruction=instruction,
        )

        assert deps.personality == personality
        assert deps.restricted_responses == restricted_responses
        assert deps.instruction == instruction


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
        metadata.get_current_time.return_value = datetime(2025, 1, 1, 15, 30, 0, tzinfo=ZoneInfo("America/New_York"))
        return metadata

    @pytest.fixture
    def mock_run_context(self, mock_user_metadata):
        """Create mock pydantic_ai run context."""
        context = MagicMock()
        context.deps = MagicMock(spec=ChatAgentDependencies)
        context.deps.tg_chat_id = "123456"
        context.deps.personality = PersonalityTypes.EXPLORATION.value
        context.deps.restricted_responses = set()
        context.deps.instruction = None

        with patch.object(UserMetadata, "get_by_user_id", return_value=mock_user_metadata):
            yield context

    @pytest.mark.asyncio
    async def test_instructions_with_default_settings(self, mock_run_context, mock_user_metadata):
        """Test instructions generation with default settings."""
        result = await instructions_with_personality_switch(mock_run_context)

        assert isinstance(result, str)

        # Verify user preferences are included
        expected_preferences = USER_PREFERENCES.format(
            preferred_name=mock_user_metadata.preferred_name,
            country=mock_user_metadata.country,
            timezone=mock_user_metadata.timezone,
            current_time=mock_user_metadata.get_current_time(),
            communication_style=mock_user_metadata.communication_style,
        )
        assert "<user_preferences>" in result
        assert "Alice" in result
        assert "America/New_York" in result
        assert "casual and friendly" in result

    @pytest.mark.asyncio
    async def test_instructions_with_restricted_text_response(self, mock_run_context):
        """Test instructions generation with restricted text responses."""
        mock_run_context.deps.restricted_responses = {"text"}

        result = await instructions_with_personality_switch(mock_run_context)

        assert "recently responded via a text response" in result
        assert "cannot do so again immediately" in result

    @pytest.mark.asyncio
    async def test_instructions_with_restricted_personality_switch(self, mock_run_context):
        """Test instructions generation with restricted personality switches."""
        mock_run_context.deps.restricted_responses = {"switch_personality"}

        result = await instructions_with_personality_switch(mock_run_context)

        assert "will not be allowed to switch personalities" in result

    @pytest.mark.asyncio
    async def test_instructions_with_multiple_restrictions(self, mock_run_context):
        """Test instructions generation with multiple restrictions."""
        mock_run_context.deps.restricted_responses = {"text", "switch_personality"}

        result = await instructions_with_personality_switch(mock_run_context)

        assert "recently responded via a text response" in result
        assert "will not be allowed to switch personalities" in result

    @pytest.mark.asyncio
    async def test_instructions_with_custom_instruction(self, mock_run_context):
        """Test instructions generation with custom instruction message."""
        instruction_message = "Please acknowledge this important message"
        mock_run_context.deps.instruction = instruction_message

        result = await instructions_with_personality_switch(mock_run_context)

        assert instruction_message in result
        assert "<message>" in result

    @pytest.mark.asyncio
    async def test_instructions_with_different_personality(self, mock_run_context):
        """Test instructions generation with different personality."""
        mock_run_context.deps.personality = PersonalityTypes.ANCHORING.value

        result = await instructions_with_personality_switch(mock_run_context)

        # Should contain anchoring personality characteristics
        assert "Grounding presence" in result or "emotional stability" in result

    @pytest.mark.asyncio
    async def test_instructions_user_metadata_called_correctly(self, mock_run_context):
        """Test that UserMetadata.get_by_user_id is called with correct chat_id."""
        with patch.object(UserMetadata, "get_by_user_id") as mock_get_user:
            mock_metadata = MagicMock(spec=UserMetadata)
            mock_metadata.preferred_name = "Test"
            mock_metadata.country = "Test"
            mock_metadata.timezone = "UTC"
            mock_metadata.communication_style = "Test"
            mock_metadata.get_current_time.return_value = None
            mock_get_user.return_value = mock_metadata

            await instructions_with_personality_switch(mock_run_context)

            mock_get_user.assert_called_once_with(mock_run_context.deps.tg_chat_id)

    @pytest.mark.asyncio
    async def test_instructions_calls_get_current_time(self, mock_run_context, mock_user_metadata):
        """Test that user metadata get_current_time method is called."""
        await instructions_with_personality_switch(mock_run_context)

        mock_user_metadata.get_current_time.assert_called_once()


class TestUpdateCommunicationStyleTool:
    """Test update_communication_style tool."""

    @pytest.fixture
    def mock_run_context(self):
        """Create mock pydantic_ai run context."""
        context = MagicMock()
        context.deps = MagicMock(spec=ChatAgentDependencies)
        context.deps.tg_chat_id = "123456"
        context.deps.tg_session_id = "session_123"
        return context

    @pytest.fixture
    def mock_anonymization_result(self):
        """Create mock anonymization agent result."""
        result = MagicMock()
        result.output = "friendly and supportive"
        return result

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.chat.async_database")
    @patch("areyouok_telegram.llms.chat.agents.chat.run_agent_with_tracking")
    async def test_update_communication_style_success(
        self, mock_run_agent, mock_async_db, mock_run_context, mock_anonymization_result
    ):
        """Test successful communication style update."""
        # Setup mocks
        mock_run_agent.return_value = mock_anonymization_result
        mock_db_conn = AsyncMock()
        mock_async_db.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_db.return_value.__aexit__ = AsyncMock(return_value=None)

        new_style = "more direct and practical"

        with patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock) as mock_update:
            result = await update_communication_style(mock_run_context, new_style)

            # Verify anonymization was called
            mock_run_agent.assert_called_once()
            args, kwargs = mock_run_agent.call_args
            assert kwargs["chat_id"] == mock_run_context.deps.tg_chat_id
            assert kwargs["session_id"] == mock_run_context.deps.tg_session_id
            assert kwargs["run_kwargs"]["user_prompt"] == new_style

            # Verify database update was called
            mock_update.assert_called_once_with(
                mock_db_conn,
                user_id=mock_run_context.deps.tg_chat_id,
                field="communication_style",
                value=mock_anonymization_result.output,
            )

            # Verify return value
            assert "friendly and supportive" in result
            assert "User's new communication_style updated to" in result

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.chat.async_database")
    @patch("areyouok_telegram.llms.chat.agents.chat.run_agent_with_tracking")
    async def test_update_communication_style_database_error(
        self, mock_run_agent, mock_async_db, mock_run_context, mock_anonymization_result
    ):
        """Test communication style update with database error."""
        # Setup mocks
        mock_run_agent.return_value = mock_anonymization_result
        mock_db_conn = AsyncMock()
        mock_async_db.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_db.return_value.__aexit__ = AsyncMock(return_value=None)

        new_style = "more formal"
        database_error = Exception("Database connection failed")

        with patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock) as mock_update:
            mock_update.side_effect = database_error

            with pytest.raises(MetadataFieldUpdateError) as exc_info:
                await update_communication_style(mock_run_context, new_style)

            # Verify exception details
            assert exc_info.value.field == "communication_style"
            assert str(database_error) in str(exc_info.value)
            assert exc_info.value.__cause__ == database_error

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.chat.async_database")
    @patch("areyouok_telegram.llms.chat.agents.chat.run_agent_with_tracking")
    async def test_update_communication_style_anonymization_called_correctly(
        self, mock_run_agent, mock_async_db, mock_run_context, mock_anonymization_result
    ):
        """Test that anonymization agent is called with correct parameters."""
        # Setup mocks
        mock_run_agent.return_value = mock_anonymization_result
        mock_db_conn = AsyncMock()
        mock_async_db.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_db.return_value.__aexit__ = AsyncMock(return_value=None)

        new_style = "casual but professional"

        with patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock):
            await update_communication_style(mock_run_context, new_style)

            # Verify anonymization agent call
            mock_run_agent.assert_called_once()
            call_args = mock_run_agent.call_args

            # First argument should be anonymization_agent
            from areyouok_telegram.llms.validators.anonymizer import anonymization_agent
            assert call_args[0][0] == anonymization_agent

            # Verify keyword arguments
            assert call_args[1]["chat_id"] == "123456"
            assert call_args[1]["session_id"] == "session_123"
            assert call_args[1]["run_kwargs"]["user_prompt"] == new_style


class TestBaseChatPromptTemplate:
    """Test BaseChatPromptTemplate functionality."""

    def test_prompt_template_creation_with_defaults(self):
        """Test BaseChatPromptTemplate creation with default values."""
        template = BaseChatPromptTemplate(response="Test response")

        assert template.response == "Test response"
        assert template.message is None
        assert template.objectives is None
        assert template.personality is None
        assert template.user_preferences is None
        # Default values should be set from constants
        assert template.identity
        assert template.rules
        assert template.knowledge

    def test_prompt_template_creation_with_user_preferences(self):
        """Test BaseChatPromptTemplate creation with user preferences."""
        user_prefs = "Preferred Name: Alice\nCountry: USA"

        template = BaseChatPromptTemplate(
            response="Test response",
            user_preferences=user_prefs
        )

        assert template.user_preferences == user_prefs

    def test_as_prompt_string_with_user_preferences(self):
        """Test as_prompt_string includes user preferences section."""
        user_prefs = "Preferred Name: Bob\nTimezone: UTC"

        template = BaseChatPromptTemplate(
            response="Test response",
            user_preferences=user_prefs
        )

        result = template.as_prompt_string()

        assert "<user_preferences>" in result
        assert user_prefs in result
        assert "</user_preferences>" in result

    def test_as_prompt_string_without_user_preferences(self):
        """Test as_prompt_string excludes user preferences when None."""
        template = BaseChatPromptTemplate(response="Test response")

        result = template.as_prompt_string()

        assert "<user_preferences>" not in result
        assert "</user_preferences>" not in result

    def test_as_prompt_string_structure_with_all_fields(self):
        """Test as_prompt_string includes all sections when provided."""
        template = BaseChatPromptTemplate(
            response="Test response",
            message="Important message",
            objectives="Test objectives",
            personality="Test personality",
            user_preferences="Test preferences"
        )

        result = template.as_prompt_string()

        # Verify all sections are present
        assert "<identity>" in result and "</identity>" in result
        assert "<rules>" in result and "</rules>" in result
        assert "<response>" in result and "</response>" in result
        assert "<knowledge>" in result and "</knowledge>" in result
        assert "<message>" in result and "</message>" in result
        assert "<objectives>" in result and "</objectives>" in result
        assert "<personality>" in result and "</personality>" in result
        assert "<user_preferences>" in result and "</user_preferences>" in result


class TestUserPreferencesConstant:
    """Test USER_PREFERENCES constant usage."""

    def test_user_preferences_template_formatting(self):
        """Test USER_PREFERENCES template can be formatted correctly."""
        formatted = USER_PREFERENCES.format(
            preferred_name="Alice",
            country="USA",
            timezone="America/New_York",
            current_time=datetime(2025, 1, 1, 15, 30, 0, tzinfo=ZoneInfo("America/New_York")),
            communication_style="casual and friendly"
        )

        assert "Preferred Name: Alice" in formatted
        assert "Country: USA" in formatted
        assert "Timezone: America/New_York" in formatted
        assert "Current Time:" in formatted
        assert "2025-01-01 15:30:00-05:00" in formatted
        assert "Communication Style: casual and friendly" in formatted

    def test_user_preferences_template_with_none_current_time(self):
        """Test USER_PREFERENCES template with None current_time."""
        formatted = USER_PREFERENCES.format(
            preferred_name="Bob",
            country="CAN",
            timezone="rather_not_say",
            current_time=None,
            communication_style="professional"
        )

        assert "Preferred Name: Bob" in formatted
        assert "Country: CAN" in formatted
        assert "Timezone: rather_not_say" in formatted
        assert "Current Time: None" in formatted
        assert "Communication Style: professional" in formatted

    def test_user_preferences_mentions_settings_command(self):
        """Test USER_PREFERENCES template mentions /settings command."""
        formatted = USER_PREFERENCES.format(
            preferred_name="Test",
            country="Test",
            timezone="UTC",
            current_time=None,
            communication_style="Test"
        )

        assert "/settings" in formatted
        assert "update their preferred name, country, and timezone" in formatted
