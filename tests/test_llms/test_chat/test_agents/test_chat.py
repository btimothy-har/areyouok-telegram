"""Tests for chat agents."""

from datetime import datetime
from unittest.mock import ANY
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from telegram.ext import ContextTypes

from areyouok_telegram.data.models.notifications import Notifications
from areyouok_telegram.data.models.user_metadata import UserMetadata
from areyouok_telegram.llms.agent_anonymizer import anonymization_agent
from areyouok_telegram.llms.chat.agents.chat import ChatAgentDependencies
from areyouok_telegram.llms.chat.agents.chat import instructions_with_personality_switch
from areyouok_telegram.llms.chat.agents.chat import update_communication_style
from areyouok_telegram.llms.chat.personalities import PersonalityTypes
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError


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
        assert deps.notification is None

    def test_dependencies_creation_with_custom_values(self):
        """Test ChatAgentDependencies creation with custom values."""
        tg_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        tg_chat_id = "123456"
        tg_session_id = "session_123"
        personality = PersonalityTypes.ANCHORING.value
        restricted_responses = {"text", "reaction"}
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = "Special instruction"

        deps = ChatAgentDependencies(
            tg_context=tg_context,
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
    async def test_instructions_with_default_settings(self, mock_run_context, mock_user_metadata):  # noqa: ARG002
        """Test instructions generation with default settings."""
        result = await instructions_with_personality_switch(mock_run_context)

        assert isinstance(result, str)

        # Verify user preferences are included
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
        """Test instructions generation with custom notification message."""
        notification_message = "Please acknowledge this important message"
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = notification_message
        mock_run_context.deps.notification = mock_notification

        result = await instructions_with_personality_switch(mock_run_context)

        assert notification_message in result
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
            mock_get_user.return_value = mock_metadata

            await instructions_with_personality_switch(mock_run_context)

            mock_get_user.assert_called_once_with(ANY, user_id=mock_run_context.deps.tg_chat_id)



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

        # Mock context logging dependencies
        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "test_encryption_key"

        new_style = "more direct and practical"

        with (
            patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock) as mock_update,
            patch("areyouok_telegram.llms.utils.Chats.get_by_id", new_callable=AsyncMock) as mock_get_chat,
            patch("areyouok_telegram.llms.utils.Context.new_or_update", new_callable=AsyncMock) as mock_context_update,
        ):
            # Setup context logging mocks
            mock_get_chat.return_value = mock_chat

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

            # Verify context logging was called (note: uses separate db connection)
            # The log_metadata_update_context creates its own db connection
            mock_get_chat.assert_called_once()
            get_chat_call = mock_get_chat.call_args
            assert get_chat_call[1]["chat_id"] == mock_run_context.deps.tg_chat_id

            mock_chat.retrieve_key.assert_called_once()

            mock_context_update.assert_called_once()
            context_call = mock_context_update.call_args
            assert context_call[1]["chat_encryption_key"] == "test_encryption_key"
            assert context_call[1]["chat_id"] == mock_run_context.deps.tg_chat_id
            assert context_call[1]["session_id"] == mock_run_context.deps.tg_session_id
            assert context_call[1]["ctype"] == "metadata"
            assert (
                context_call[1]["content"]
                == f"Updated usermeta: communication_style is now {mock_anonymization_result.output}"
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

        # Mock context logging dependencies
        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "test_encryption_key"

        new_style = "casual but professional"

        with (
            patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock),
            patch("areyouok_telegram.llms.utils.Chats.get_by_id", new_callable=AsyncMock) as mock_get_chat,
            patch("areyouok_telegram.llms.utils.Context.new_or_update", new_callable=AsyncMock),
        ):
            # Setup context logging mocks
            mock_get_chat.return_value = mock_chat

            await update_communication_style(mock_run_context, new_style)

            # Verify anonymization agent call
            mock_run_agent.assert_called_once()
            call_args = mock_run_agent.call_args

            # First argument should be anonymization_agent

            assert call_args[0][0] == anonymization_agent

            # Verify keyword arguments
            assert call_args[1]["chat_id"] == "123456"
            assert call_args[1]["session_id"] == "session_123"
            assert call_args[1]["run_kwargs"]["user_prompt"] == new_style
