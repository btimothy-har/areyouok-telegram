"""Tests for llms/agent_preferences.py using pydantic_ai testing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pydantic_ai
import pytest
from pydantic_ai import models

from areyouok_telegram.llms.agent_preferences import (
    FeedbackMissingError,
    PreferencesAgentDependencies,
    PreferencesUpdateResponse,
    preferences_agent,
    update_preferred_name,
    validate_preferences_agent_output,
)
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


class TestPreferencesAgentDependencies:
    """Test PreferencesAgentDependencies dataclass."""

    def test_preferences_agent_dependencies_creation(self):
        """Test PreferencesAgentDependencies can be created with required fields."""
        deps = PreferencesAgentDependencies(tg_chat_id="123456789", tg_session_id="session_456")

        assert deps.tg_chat_id == "123456789"
        assert deps.tg_session_id == "session_456"

    def test_preferences_agent_dependencies_fields_required(self):
        """Test that all fields are required."""
        # Should raise TypeError if required fields are missing
        with pytest.raises(TypeError):
            PreferencesAgentDependencies()  # Missing required fields


class TestPreferencesUpdateResponse:
    """Test PreferencesUpdateResponse model."""

    def test_preferences_update_response_creation(self):
        """Test PreferencesUpdateResponse can be created."""
        response = PreferencesUpdateResponse(completed=True, feedback="Successfully updated your preferences.")

        assert response.completed is True
        assert response.feedback == "Successfully updated your preferences."

    def test_preferences_update_response_defaults(self):
        """Test PreferencesUpdateResponse has correct default values."""
        response = PreferencesUpdateResponse(completed=True)

        assert response.completed is True
        assert response.feedback is None

    def test_preferences_update_response_validation(self):
        """Test PreferencesUpdateResponse validates field types."""
        # Test with invalid types
        with pytest.raises(ValueError):
            PreferencesUpdateResponse(completed="not a boolean")


