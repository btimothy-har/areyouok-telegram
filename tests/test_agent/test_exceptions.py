"""Tests for agent exception classes."""

import pytest
from pydantic_ai import ModelRetry

from areyouok_telegram.agent.exceptions import InvalidMessageError
from areyouok_telegram.agent.exceptions import ReactToSelfError


class TestInvalidMessageError:
    """Test suite for InvalidMessageError exception."""

    def test_invalid_message_error_creation(self):
        """Test creating InvalidMessageError with message ID."""
        message_id = "123456"
        error = InvalidMessageError(message_id)

        assert error.message_id == message_id
        assert f"Message with ID {message_id} not found" in str(error)

    def test_invalid_message_error_str_representation(self):
        """Test string representation of InvalidMessageError."""
        message_id = "789"
        error = InvalidMessageError(message_id)

        expected_message = f"Message with ID {message_id} not found."
        assert str(error) == expected_message

    def test_invalid_message_error_inheritance(self):
        """Test that InvalidMessageError inherits from ModelRetry."""
        error = InvalidMessageError("test_id")
        assert isinstance(error, ModelRetry)

    def test_invalid_message_error_with_different_ids(self):
        """Test InvalidMessageError with various message ID formats."""
        test_cases = [
            "123",
            "message_456",
            "very_long_message_id_12345678",
            "0",
        ]

        for message_id in test_cases:
            error = InvalidMessageError(message_id)
            assert error.message_id == message_id
            assert message_id in str(error)


class TestReactToSelfError:
    """Test suite for ReactToSelfError exception."""

    def test_react_to_self_error_creation(self):
        """Test creating ReactToSelfError with message ID."""
        message_id = "987654"
        error = ReactToSelfError(message_id)

        assert error.message_id == message_id
        assert f"You cannot react to your own message {message_id}" in str(error)

    def test_react_to_self_error_str_representation(self):
        """Test string representation of ReactToSelfError."""
        message_id = "321"
        error = ReactToSelfError(message_id)

        expected_message = f"You cannot react to your own message {message_id}."
        assert str(error) == expected_message

    def test_react_to_self_error_inheritance(self):
        """Test that ReactToSelfError inherits from ModelRetry."""
        error = ReactToSelfError("test_id")
        assert isinstance(error, ModelRetry)

    def test_react_to_self_error_with_different_ids(self):
        """Test ReactToSelfError with various message ID formats."""
        test_cases = [
            "999",
            "self_message_123",
            "bot_response_456",
            "12345",
        ]

        for message_id in test_cases:
            error = ReactToSelfError(message_id)
            assert error.message_id == message_id
            assert message_id in str(error)

    def test_both_exceptions_are_model_retry_subclasses(self):
        """Test that both exceptions are subclasses of ModelRetry for proper retry behavior."""
        invalid_msg_error = InvalidMessageError("123")
        react_self_error = ReactToSelfError("456")

        # Both should be ModelRetry instances for proper agent retry behavior
        assert isinstance(invalid_msg_error, ModelRetry)
        assert isinstance(react_self_error, ModelRetry)

        # Verify they can be caught as ModelRetry
        with pytest.raises(ModelRetry):
            raise invalid_msg_error

        with pytest.raises(ModelRetry):
            raise react_self_error
