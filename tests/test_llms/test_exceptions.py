"""Tests for LLM-related exceptions."""

import pydantic_ai

from areyouok_telegram.llms.exceptions import BaseModelError
from areyouok_telegram.llms.exceptions import CompleteOnboardingError
from areyouok_telegram.llms.exceptions import InvalidMessageError
from areyouok_telegram.llms.exceptions import InvalidPersonalityError
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError
from areyouok_telegram.llms.exceptions import ModelConfigurationError
from areyouok_telegram.llms.exceptions import ModelInputError
from areyouok_telegram.llms.exceptions import ReactToSelfError
from areyouok_telegram.llms.exceptions import ResponseRestrictedError
from areyouok_telegram.llms.exceptions import UnacknowledgedImportantMessageError


class TestBaseModelError:
    """Test BaseModelError exception."""

    def test_base_model_error_is_exception(self):
        """Test BaseModelError inherits from Exception."""
        error = BaseModelError("Test message")
        assert isinstance(error, Exception)

    def test_base_model_error_message(self):
        """Test BaseModelError accepts custom message."""
        message = "Test error message"
        error = BaseModelError(message)
        assert str(error) == message


class TestModelInputError:
    """Test ModelInputError exception."""

    def test_model_input_error_inheritance(self):
        """Test ModelInputError inherits from BaseModelError."""
        error = ModelInputError()
        assert isinstance(error, BaseModelError)
        assert isinstance(error, Exception)

    def test_model_input_error_default_message(self):
        """Test ModelInputError has default message."""
        error = ModelInputError()
        expected_message = "Either model_id or openrouter_id must be provided."
        assert str(error) == expected_message


class TestModelConfigurationError:
    """Test ModelConfigurationError exception."""

    def test_model_configuration_error_inheritance(self):
        """Test ModelConfigurationError inherits from BaseModelError."""
        error = ModelConfigurationError()
        assert isinstance(error, BaseModelError)
        assert isinstance(error, Exception)

    def test_model_configuration_error_default_message(self):
        """Test ModelConfigurationError has default message."""
        error = ModelConfigurationError()
        expected_message = "No valid model configuration found. Ensure either primary or OpenRouter model is set."
        assert str(error) == expected_message


class TestInvalidMessageError:
    """Test InvalidMessageError exception."""

    def test_invalid_message_error_inheritance(self):
        """Test InvalidMessageError inherits from pydantic_ai.ModelRetry."""
        error = InvalidMessageError("test_message_id")
        assert isinstance(error, pydantic_ai.ModelRetry)

    def test_invalid_message_error_attributes(self):
        """Test InvalidMessageError stores message_id attribute."""
        message_id = "test_message_123"
        error = InvalidMessageError(message_id)
        assert error.message_id == message_id
        assert f"Message with ID {message_id} not found." in str(error)


class TestReactToSelfError:
    """Test ReactToSelfError exception."""

    def test_react_to_self_error_inheritance(self):
        """Test ReactToSelfError inherits from pydantic_ai.ModelRetry."""
        error = ReactToSelfError("test_message_id")
        assert isinstance(error, pydantic_ai.ModelRetry)

    def test_react_to_self_error_attributes(self):
        """Test ReactToSelfError stores message_id attribute."""
        message_id = "test_message_456"
        error = ReactToSelfError(message_id)
        assert error.message_id == message_id
        assert f"You cannot react to your own message {message_id}." in str(error)


class TestResponseRestrictedError:
    """Test ResponseRestrictedError exception."""

    def test_response_restricted_error_inheritance(self):
        """Test ResponseRestrictedError inherits from pydantic_ai.ModelRetry."""
        error = ResponseRestrictedError("text")
        assert isinstance(error, pydantic_ai.ModelRetry)

    def test_response_restricted_error_attributes(self):
        """Test ResponseRestrictedError stores response_type attribute."""
        response_type = "text"
        error = ResponseRestrictedError(response_type)
        assert error.response_type == response_type
        expected_message = f"Response of type {response_type} is restricted for this conversation. Use a different response type."
        assert expected_message in str(error)


class TestUnacknowledgedImportantMessageError:
    """Test UnacknowledgedImportantMessageError exception."""

    def test_unacknowledged_important_message_error_inheritance(self):
        """Test UnacknowledgedImportantMessageError inherits from pydantic_ai.ModelRetry."""
        error = UnacknowledgedImportantMessageError("test message")
        assert isinstance(error, pydantic_ai.ModelRetry)

    def test_unacknowledged_important_message_error_with_message_only(self):
        """Test UnacknowledgedImportantMessageError with message only."""
        message = "Important message not acknowledged"
        error = UnacknowledgedImportantMessageError(message)
        assert error.message == message
        assert error.feedback == ""
        assert f"Important message not acknowledged: {message}. " in str(error)

    def test_unacknowledged_important_message_error_with_feedback(self):
        """Test UnacknowledgedImportantMessageError with message and feedback."""
        message = "Important message"
        feedback = "Please acknowledge this message"
        error = UnacknowledgedImportantMessageError(message, feedback)
        assert error.message == message
        assert error.feedback == feedback
        assert f"Important message not acknowledged: {message}. {feedback}" in str(error)


class TestInvalidPersonalityError:
    """Test InvalidPersonalityError exception."""

    def test_invalid_personality_error_inheritance(self):
        """Test InvalidPersonalityError inherits from ValueError."""
        error = InvalidPersonalityError("invalid_personality")
        assert isinstance(error, ValueError)
        assert isinstance(error, Exception)

    def test_invalid_personality_error_attributes(self):
        """Test InvalidPersonalityError stores personality attribute."""
        personality = "invalid_personality"
        error = InvalidPersonalityError(personality)
        assert error.personality == personality
        assert f"Invalid personality type: {personality}." in str(error)


class TestMetadataFieldUpdateError:
    """Test MetadataFieldUpdateError exception."""

    def test_metadata_field_update_error_inheritance(self):
        """Test MetadataFieldUpdateError inherits from pydantic_ai.ModelRetry."""
        error = MetadataFieldUpdateError("test_field")
        assert isinstance(error, pydantic_ai.ModelRetry)

    def test_metadata_field_update_error_with_field_only(self):
        """Test MetadataFieldUpdateError with field name only."""
        field = "communication_style"
        error = MetadataFieldUpdateError(field)
        assert error.field == field
        assert f"Error updating field: {field}. " in str(error)

    def test_metadata_field_update_error_with_field_and_message(self):
        """Test MetadataFieldUpdateError with field name and custom message."""
        field = "preferred_name"
        message = "Database connection failed"
        error = MetadataFieldUpdateError(field, message)
        assert error.field == field
        assert f"Error updating field: {field}. {message}" in str(error)

    def test_metadata_field_update_error_with_none_message(self):
        """Test MetadataFieldUpdateError with None message."""
        field = "timezone"
        error = MetadataFieldUpdateError(field, None)
        assert error.field == field
        assert f"Error updating field: {field}. " in str(error)


class TestCompleteOnboardingError:
    """Test CompleteOnboardingError exception."""

    def test_complete_onboarding_error_inheritance(self):
        """Test CompleteOnboardingError inherits from pydantic_ai.ModelRetry."""
        error = CompleteOnboardingError("test message")
        assert isinstance(error, pydantic_ai.ModelRetry)

    def test_complete_onboarding_error_message(self):
        """Test CompleteOnboardingError stores message correctly."""
        message = "Failed to complete onboarding process"
        error = CompleteOnboardingError(message)
        assert f"Error completing onboarding: {message}" in str(error)
