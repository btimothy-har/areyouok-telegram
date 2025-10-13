"""Tests for chat agents."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from areyouok_telegram.data.models.notifications import Notifications
from areyouok_telegram.data.models.user_metadata import UserMetadata
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
    @patch("areyouok_telegram.llms.chat.agents.chat.run_agent_with_tracking")
    async def test_update_communication_style_success(
        self, mock_run_agent, mock_run_context, mock_anonymization_result, mock_db_session
    ):
        """Test successful communication style update."""
        # Setup mocks
        mock_run_agent.return_value = mock_anonymization_result

        # Mock context logging dependencies
        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "test_encryption_key"

        new_style = "more direct and practical"

        with (
            patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock) as mock_update,
            patch("areyouok_telegram.llms.utils.Chats.get_by_id", new_callable=AsyncMock) as mock_get_chat,
            patch("areyouok_telegram.llms.utils.Context.new", new_callable=AsyncMock) as mock_context_update,
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

            # Verify database update was called (uses conftest mock_db_session)
            mock_update.assert_called_once_with(
                mock_db_session,
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
    @patch("areyouok_telegram.llms.chat.agents.chat.run_agent_with_tracking")
    async def test_update_communication_style_database_error(
        self, mock_run_agent, mock_run_context, mock_anonymization_result
    ):
        """Test communication style update with database error."""
        # Setup mocks
        mock_run_agent.return_value = mock_anonymization_result

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
    @patch("areyouok_telegram.llms.chat.agents.chat.run_agent_with_tracking")
    async def test_update_communication_style_anonymization_called_correctly(
        self, mock_run_agent, mock_run_context, mock_anonymization_result
    ):
        """Test that anonymization agent is called with correct parameters."""
        # Setup mocks
        mock_run_agent.return_value = mock_anonymization_result

        # Mock context logging dependencies
        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "test_encryption_key"

        new_style = "casual but professional"

        with (
            patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock),
            patch("areyouok_telegram.llms.utils.Chats.get_by_id", new_callable=AsyncMock) as mock_get_chat,
            patch("areyouok_telegram.llms.utils.Context.new", new_callable=AsyncMock),
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


class TestGetCurrentTimeTool:
    """Test get_current_time tool."""

    @pytest.fixture
    def mock_run_context(self):
        """Create mock pydantic_ai run context."""
        context = MagicMock()
        context.deps = MagicMock(spec=ChatAgentDependencies)
        context.deps.tg_chat_id = "123456"
        return context

    @pytest.fixture
    def mock_user_metadata_with_timezone(self):
        """Create mock user metadata with valid timezone."""
        metadata = MagicMock(spec=UserMetadata)
        metadata.timezone = "America/New_York"
        return metadata

    @pytest.fixture
    def mock_user_metadata_no_timezone(self):
        """Create mock user metadata with no timezone set."""
        metadata = MagicMock(spec=UserMetadata)
        metadata.timezone = None
        return metadata

    @pytest.fixture
    def mock_user_metadata_invalid_timezone(self):
        """Create mock user metadata with invalid timezone."""
        metadata = MagicMock(spec=UserMetadata)
        metadata.timezone = "Invalid/Timezone"
        return metadata

    @pytest.mark.asyncio
    @freeze_time("2024-01-15 14:30:45")
    async def test_get_current_time_with_valid_timezone(
        self, mock_run_context, mock_user_metadata_with_timezone, mock_db_session
    ):
        """Test get_current_time with user having valid timezone."""
        with patch.object(UserMetadata, "get_by_user_id", new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user_metadata_with_timezone

            result = await get_current_time(mock_run_context)

            # Verify database call (uses conftest mock_db_session)
            mock_get_user.assert_called_once_with(mock_db_session, user_id="123456")

            # Verify result contains expected time information
            assert "America/New_York" in result
            assert "Current time in the user's timezone" in result
            assert "2024-01-15" in result
            # Time should be converted from UTC to EST (UTC-5)
            assert "09:30" in result or "EST" in result

    @pytest.mark.asyncio
    async def test_get_current_time_with_no_timezone(
        self, mock_run_context, mock_user_metadata_no_timezone, mock_db_session
    ):
        """Test get_current_time when user has no timezone set."""
        with patch.object(UserMetadata, "get_by_user_id", new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user_metadata_no_timezone

            result = await get_current_time(mock_run_context)

            # Verify database call (uses conftest mock_db_session)
            mock_get_user.assert_called_once_with(mock_db_session, user_id="123456")

            # Verify error message is returned
            assert result == "The user's timezone is not set or invalid, so the current time cannot be determined."

    @pytest.mark.asyncio
    @freeze_time("2024-01-15 20:15:30")
    async def test_get_current_time_with_invalid_timezone(
        self, mock_run_context, mock_user_metadata_invalid_timezone, mock_db_session
    ):
        """Test get_current_time when user has invalid timezone."""
        with patch.object(UserMetadata, "get_by_user_id", new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user_metadata_invalid_timezone

            result = await get_current_time(mock_run_context)

            # Verify database call (uses conftest mock_db_session)
            mock_get_user.assert_called_once_with(mock_db_session, user_id="123456")

            # Verify error message is returned when timezone is invalid
            assert result == "The user's timezone is not set or invalid, so the current time cannot be determined."

    @pytest.mark.asyncio
    @freeze_time("2024-07-20 12:00:00")  # Summer time for DST testing
    async def test_get_current_time_with_dst_timezone(self, mock_run_context, mock_db_session):
        """Test get_current_time with timezone that observes DST."""
        # Create metadata with DST-observing timezone
        mock_metadata = MagicMock(spec=UserMetadata)
        mock_metadata.timezone = "America/New_York"

        with patch.object(UserMetadata, "get_by_user_id", new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_metadata

            result = await get_current_time(mock_run_context)

            # Verify database call (uses conftest mock_db_session)
            mock_get_user.assert_called_once_with(mock_db_session, user_id="123456")

            # Verify result contains expected time information
            assert "America/New_York" in result
            assert "Current time in the user's timezone" in result
            assert "2024-07-20" in result
            # Time should be converted from UTC to EDT (UTC-4 during summer)
            assert "08:00" in result or "EDT" in result

    @pytest.mark.asyncio
    @freeze_time("2024-01-15 09:45:15")
    async def test_get_current_time_with_utc_timezone(self, mock_run_context, mock_db_session):
        """Test get_current_time with UTC timezone."""
        # Create metadata with UTC timezone
        mock_metadata = MagicMock(spec=UserMetadata)
        mock_metadata.timezone = "UTC"

        with patch.object(UserMetadata, "get_by_user_id", new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_metadata

            result = await get_current_time(mock_run_context)

            # Verify database call (uses conftest mock_db_session)
            mock_get_user.assert_called_once_with(mock_db_session, user_id="123456")

            # Verify result contains expected time information
            assert "UTC" in result
            assert "Current time in the user's timezone" in result
            assert "2024-01-15 09:45 UTC" in result

    @pytest.mark.asyncio
    async def test_get_current_time_database_called_correctly(self, mock_run_context, mock_db_session):
        """Test that UserMetadata.get_by_user_id is called with correct parameters."""
        mock_metadata = MagicMock(spec=UserMetadata)
        mock_metadata.timezone = None

        with patch.object(UserMetadata, "get_by_user_id", new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_metadata

            await get_current_time(mock_run_context)

            # Verify method call (uses conftest mock_db_session)
            mock_get_user.assert_called_once_with(mock_db_session, user_id=mock_run_context.deps.tg_chat_id)

    @pytest.mark.asyncio
    @freeze_time("2024-03-10 12:00:00")  # Use noon UTC to avoid date changes in timezones
    async def test_get_current_time_with_different_timezones(self, mock_run_context):
        """Test get_current_time with various valid timezones."""
        test_timezones = [
            "Europe/London",
            "Asia/Tokyo",
            "Australia/Sydney",
            "America/Los_Angeles",
        ]

        for timezone_name in test_timezones:
            mock_metadata = MagicMock(spec=UserMetadata)
            mock_metadata.timezone = timezone_name

            with patch.object(UserMetadata, "get_by_user_id", new_callable=AsyncMock) as mock_get_user:
                mock_get_user.return_value = mock_metadata

                result = await get_current_time(mock_run_context)

                # Verify result contains timezone information
                assert timezone_name in result
                assert "Current time in the user's timezone" in result
                assert "2024-03-" in result  # Should contain the date, but day might vary by timezone

    @pytest.mark.asyncio
    async def test_get_current_time_exception_handling(self, mock_run_context):
        """Test that ZoneInfo exceptions are properly handled."""
        mock_metadata = MagicMock(spec=UserMetadata)
        mock_metadata.timezone = "Definitely/NotAValidTimezone"

        with patch.object(UserMetadata, "get_by_user_id", new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_metadata

            result = await get_current_time(mock_run_context)

            # Verify error message is returned
            assert result == "The user's timezone is not set or invalid, so the current time cannot be determined."


class TestMemoryTools:
    """Test memory and search history tools."""

    @pytest.fixture
    def mock_run_context(self):
        """Create mock pydantic_ai run context for memory tools."""
        context = MagicMock()
        context.deps = ChatAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="chat456",
            tg_session_id="session789",
        )
        return context

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.chat.update_memory_impl")
    async def test_update_memory_tool(self, mock_impl, mock_run_context):
        """Test update_memory tool calls shared implementation."""
        mock_impl.return_value = "Information committed to memory: User loves hiking"

        result = await update_memory(mock_run_context, "User loves hiking")

        assert result == "Information committed to memory: User loves hiking"
        mock_impl.assert_called_once_with(mock_run_context.deps, "User loves hiking")

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.chat.update_memory_impl")
    async def test_update_memory_with_complex_content(self, mock_impl, mock_run_context):
        """Test update_memory with complex memory content."""
        complex_memory = "User mentioned they have anxiety about public speaking and prefer written communication"
        mock_impl.return_value = f"Information committed to memory: {complex_memory}"

        result = await update_memory(mock_run_context, complex_memory)

        mock_impl.assert_called_once()
        assert complex_memory in result

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.chat.search_history_impl")
    async def test_search_history_tool(self, mock_impl, mock_run_context):
        """Test search_history tool calls shared implementation."""
        mock_impl.return_value = "**Answer:** User felt anxious about work deadlines"

        result = await search_history(mock_run_context, "times user felt anxious")

        assert result == "**Answer:** User felt anxious about work deadlines"
        mock_impl.assert_called_once_with(mock_run_context.deps, "times user felt anxious")

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.chat.search_history_impl")
    async def test_search_history_with_no_results(self, mock_impl, mock_run_context):
        """Test search_history when no results found."""
        mock_impl.return_value = "No relevant past conversations found for: test query"

        result = await search_history(mock_run_context, "test query")

        assert "No relevant past conversations found" in result
        mock_impl.assert_called_once()
