"""Tests for setup.exceptions module."""

import pytest

from areyouok_telegram.setup.exceptions import BotDescriptionSetupError
from areyouok_telegram.setup.exceptions import BotNameSetupError
from areyouok_telegram.setup.exceptions import BotSetupError


class TestBotSetupError:
    """Test cases for BotSetupError base exception."""

    def test_bot_setup_error_is_exception(self):
        """Test BotSetupError inherits from Exception."""
        # Act
        error = BotSetupError("Test message")

        # Assert
        assert isinstance(error, Exception)

    def test_bot_setup_error_message(self):
        """Test BotSetupError stores message correctly."""
        # Arrange
        message = "Custom setup error message"

        # Act
        error = BotSetupError(message)

        # Assert
        assert str(error) == message


class TestBotNameSetupError:
    """Test cases for BotNameSetupError exception."""

    def test_bot_name_setup_error_inherits_from_bot_setup_error(self):
        """Test BotNameSetupError inherits from BotSetupError."""
        # Act
        error = BotNameSetupError("TestBot")

        # Assert
        assert isinstance(error, BotSetupError)
        assert isinstance(error, Exception)

    def test_bot_name_setup_error_message_format(self):
        """Test BotNameSetupError formats message with bot name."""
        # Arrange
        bot_name = "My Test Bot"

        # Act
        error = BotNameSetupError(bot_name)

        # Assert
        expected_message = f"Failed to set bot name to '{bot_name}'. Please check your bot token and permissions."
        assert str(error) == expected_message

    def test_bot_name_setup_error_with_special_characters(self):
        """Test BotNameSetupError handles bot names with special characters."""
        # Arrange
        bot_name = "Bot [test] & symbols!"

        # Act
        error = BotNameSetupError(bot_name)

        # Assert
        expected_message = f"Failed to set bot name to '{bot_name}'. Please check your bot token and permissions."
        assert str(error) == expected_message

    def test_bot_name_setup_error_with_empty_name(self):
        """Test BotNameSetupError handles empty bot name."""
        # Arrange
        bot_name = ""

        # Act
        error = BotNameSetupError(bot_name)

        # Assert
        expected_message = "Failed to set bot name to ''. Please check your bot token and permissions."
        assert str(error) == expected_message


class TestBotDescriptionSetupError:
    """Test cases for BotDescriptionSetupError exception."""

    def test_bot_description_setup_error_inherits_from_bot_setup_error(self):
        """Test BotDescriptionSetupError inherits from BotSetupError."""
        # Act
        error = BotDescriptionSetupError()

        # Assert
        assert isinstance(error, BotSetupError)
        assert isinstance(error, Exception)

    def test_bot_description_setup_error_message(self):
        """Test BotDescriptionSetupError has the correct default message."""
        # Act
        error = BotDescriptionSetupError()

        # Assert
        expected_message = "Failed to set bot description. Please check your bot token and permissions."
        assert str(error) == expected_message

    def test_bot_description_setup_error_no_parameters_required(self):
        """Test BotDescriptionSetupError can be instantiated without parameters."""
        # Act & Assert - Should not raise any exception
        error = BotDescriptionSetupError()
        assert error is not None


class TestExceptionHierarchy:
    """Test cases for the exception hierarchy."""

    def test_all_exceptions_can_be_caught_by_base_class(self):
        """Test all custom exceptions can be caught by BotSetupError."""
        # Arrange
        exceptions = [
            BotNameSetupError("test"),
            BotDescriptionSetupError(),
        ]

        # Act & Assert
        for exception in exceptions:
            try:
                raise exception
            except BotSetupError:
                # Should catch all custom exceptions
                pass
            else:
                pytest.fail(f"Exception {type(exception)} not caught by BotSetupError")

    def test_specific_exceptions_can_be_caught_individually(self):
        """Test specific exceptions can be caught by their specific type."""
        # Test BotNameSetupError
        try:
            raise BotNameSetupError("test")
        except BotNameSetupError:
            pass
        else:
            pytest.fail("BotNameSetupError not caught by its specific type")

        # Test BotDescriptionSetupError
        try:
            raise BotDescriptionSetupError()
        except BotDescriptionSetupError:
            pass
        else:
            pytest.fail("BotDescriptionSetupError not caught by its specific type")
