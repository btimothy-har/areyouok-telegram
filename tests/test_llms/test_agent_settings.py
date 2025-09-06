"""Tests for llms/agent_settings.py using pydantic_ai testing."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pydantic_ai
import pytest
from pydantic_ai import models

from areyouok_telegram.llms.agent_settings import FeedbackMissingError
from areyouok_telegram.llms.agent_settings import SettingsAgentDependencies
from areyouok_telegram.llms.agent_settings import SettingsUpdateResponse
from areyouok_telegram.llms.agent_settings import settings_agent
from areyouok_telegram.llms.agent_settings import update_preferred_name
from areyouok_telegram.llms.agent_settings import validate_settings_agent_output
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError

# Block real model requests in tests
models.ALLOW_MODEL_REQUESTS = False
pytestmark = pytest.mark.anyio  # Mark all tests as async


class TestFeedbackMissingError:
    """Test FeedbackMissingError exception."""

    def test_feedback_missing_error_creation(self):
        """Test FeedbackMissingError is properly created."""
        error = FeedbackMissingError()

        assert isinstance(error, pydantic_ai.ModelRetry)
        assert str(error) == "Feedback is required when completed is False."

    def test_feedback_missing_error_inheritance(self):
        """Test FeedbackMissingError inherits from ModelRetry."""
        error = FeedbackMissingError()
        assert isinstance(error, pydantic_ai.ModelRetry)


class TestSettingsAgentDependencies:
    """Test SettingsAgentDependencies dataclass."""

    def test_settings_agent_dependencies_creation(self):
        """Test SettingsAgentDependencies can be created with required fields."""
        deps = SettingsAgentDependencies(tg_chat_id="123456789", tg_session_id="session_456")

        assert deps.tg_chat_id == "123456789"
        assert deps.tg_session_id == "session_456"

    def test_settings_agent_dependencies_fields_required(self):
        """Test that all fields are required."""
        # Should raise TypeError if required fields are missing
        with pytest.raises(TypeError):
            SettingsAgentDependencies()  # Missing required fields


class TestSettingsUpdateResponse:
    """Test SettingsUpdateResponse model."""

    def test_settings_update_response_creation(self):
        """Test SettingsUpdateResponse can be created."""
        response = SettingsUpdateResponse(completed=True, feedback="Successfully updated your settings.")

        assert response.completed is True
        assert response.feedback == "Successfully updated your settings."

    def test_settings_update_response_defaults(self):
        """Test SettingsUpdateResponse has correct default values."""
        response = SettingsUpdateResponse(completed=True)

        assert response.completed is True
        assert response.feedback is None

    def test_settings_update_response_validation(self):
        """Test SettingsUpdateResponse validates field types."""
        # Test with invalid types
        with pytest.raises(ValueError):
            SettingsUpdateResponse(completed="not a boolean")


class TestSettingsAgentTools:
    """Test settings agent tool functions."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock context for agent tools."""
        mock_ctx = MagicMock()
        mock_deps = SettingsAgentDependencies(tg_chat_id="123456789", tg_session_id="session_456")
        mock_ctx.deps = mock_deps
        return mock_ctx

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.agent_settings.async_database")
    @patch("areyouok_telegram.llms.agent_settings.UserMetadata.update_metadata")
    @patch("areyouok_telegram.llms.agent_settings.log_metadata_update_context")
    async def test_update_preferred_name_success(
        self, mock_log_context, mock_update_metadata, mock_async_database, mock_context
    ):
        """Test successful preferred name update."""
        # Setup database mock
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        # Call function
        result = await update_preferred_name(mock_context, "Alice Smith")

        # Verify database update was called
        mock_update_metadata.assert_called_once_with(
            mock_db_conn,
            user_id=mock_context.deps.tg_chat_id,
            field="preferred_name",
            value="Alice Smith",
        )

        # Verify context logging
        mock_log_context.assert_called_once_with(
            chat_id=mock_context.deps.tg_chat_id,
            session_id=mock_context.deps.tg_session_id,
            content="Updated user settings: preferred_name is now Alice Smith",
        )

        # Verify return value
        assert result == "preferred_name updated successfully to Alice Smith."

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.agent_settings.async_database")
    @patch("areyouok_telegram.llms.agent_settings.UserMetadata.update_metadata")
    async def test_update_preferred_name_database_error(self, mock_update_metadata, mock_async_database, mock_context):
        """Test preferred name update with database error."""
        # Setup database mock
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock database error
        database_error = Exception("Database update failed")
        mock_update_metadata.side_effect = database_error

        # Should raise MetadataFieldUpdateError
        with pytest.raises(MetadataFieldUpdateError) as exc_info:
            await update_preferred_name(mock_context, "Alice")

        # Verify exception details
        error = exc_info.value
        assert error.field == "preferred_name"
        assert error.__cause__ == database_error


class TestSettingsAgentValidation:
    """Test settings agent output validation."""

    @pytest.mark.asyncio
    async def test_validate_settings_agent_output_completed_true(self):
        """Test validation passes when completed is True."""
        mock_ctx = MagicMock()

        response = SettingsUpdateResponse(completed=True, feedback="Success!")
        result = await validate_settings_agent_output(mock_ctx, response)

        assert result == response
        assert result.completed is True
        assert result.feedback == "Success!"

    @pytest.mark.asyncio
    async def test_validate_settings_agent_output_completed_false_no_feedback_raises_error(self):
        """Test validation raises error when completed is False and no feedback provided."""
        mock_ctx = MagicMock()

        response = SettingsUpdateResponse(completed=False, feedback=None)

        with pytest.raises(FeedbackMissingError):
            await validate_settings_agent_output(mock_ctx, response)


class TestSettingsAgent:
    """Test the settings agent configuration (unit tests only)."""

    def test_settings_agent_configuration(self):
        """Test that settings agent is properly configured."""
        # Verify agent properties
        assert settings_agent.name == "settings_agent"
        assert settings_agent.output_type == SettingsUpdateResponse
        assert settings_agent.end_strategy == "exhaustive"

        # Verify model is configured
        assert hasattr(settings_agent, "model")

    def test_settings_agent_dependencies_structure(self):
        """Test SettingsAgentDependencies structure."""
        chat_id = "test_chat_123"
        session_id = "test_session_456"

        deps = SettingsAgentDependencies(tg_chat_id=chat_id, tg_session_id=session_id)

        # Verify dependencies structure
        assert deps.tg_chat_id == chat_id
        assert deps.tg_session_id == session_id
