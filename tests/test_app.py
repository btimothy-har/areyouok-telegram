"""Tests for the app module."""

from unittest.mock import Mock
from unittest.mock import patch

import pytest
from telegram.ext import Application

from areyouok_telegram.app import application_startup
from areyouok_telegram.app import create_application
from areyouok_telegram.setup.exceptions import BotDescriptionSetupError
from areyouok_telegram.setup.exceptions import BotNameSetupError


class TestApplicationStartup:
    """Test cases for application_startup function."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.app.setup_bot_name")
    @patch("areyouok_telegram.app.setup_bot_description")
    async def test_application_startup_success(self, mock_setup_description, mock_setup_name):
        """Test successful application startup calls both setup functions."""
        # Arrange
        mock_application = Mock(spec=Application)
        mock_setup_name.return_value = None
        mock_setup_description.return_value = None

        # Act
        await application_startup(mock_application)

        # Assert
        mock_setup_name.assert_called_once_with(mock_application)
        mock_setup_description.assert_called_once_with(mock_application)

    @pytest.mark.asyncio
    @patch("areyouok_telegram.app.setup_bot_name")
    @patch("areyouok_telegram.app.setup_bot_description")
    async def test_application_startup_name_failure_propagates_exception(
        self, mock_setup_description, mock_setup_name
    ):
        """Test application startup propagates BotNameSetupError."""
        # Arrange
        mock_application = Mock(spec=Application)
        mock_setup_name.side_effect = BotNameSetupError("Test Bot")

        # Act & Assert
        with pytest.raises(BotNameSetupError):
            await application_startup(mock_application)

        # Should not call description setup if name setup fails
        mock_setup_description.assert_not_called()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.app.setup_bot_name")
    @patch("areyouok_telegram.app.setup_bot_description")
    async def test_application_startup_description_failure_propagates_exception(
        self, mock_setup_description, mock_setup_name
    ):
        """Test application startup propagates BotDescriptionSetupError."""
        # Arrange
        mock_application = Mock(spec=Application)
        mock_setup_name.return_value = None
        mock_setup_description.side_effect = BotDescriptionSetupError()

        # Act & Assert
        with pytest.raises(BotDescriptionSetupError):
            await application_startup(mock_application)

        # Name setup should complete successfully
        mock_setup_name.assert_called_once_with(mock_application)


class TestCreateApplication:
    """Test cases for create_application function."""

    @patch("areyouok_telegram.app.asyncio.set_event_loop_policy")
    @patch("areyouok_telegram.app.logging_setup")
    @patch("areyouok_telegram.app.database_setup")
    @patch("areyouok_telegram.app.ApplicationBuilder")
    def test_create_application_configures_infrastructure(
        self, mock_builder, mock_db_setup, mock_log_setup, mock_set_policy
    ):
        """Test create_application sets up infrastructure correctly."""
        # Arrange
        mock_application = Mock(spec=Application)
        mock_builder_instance = Mock()
        mock_builder.return_value = mock_builder_instance
        mock_builder_instance.token.return_value = mock_builder_instance
        mock_builder_instance.concurrent_updates.return_value = mock_builder_instance
        mock_builder_instance.post_init.return_value = mock_builder_instance
        mock_builder_instance.build.return_value = mock_application

        # Act
        result = create_application()

        # Assert
        mock_set_policy.assert_called_once()
        mock_log_setup.assert_called_once()
        mock_db_setup.assert_called_once()
        assert result == mock_application

    @patch("areyouok_telegram.app.asyncio.set_event_loop_policy")
    @patch("areyouok_telegram.app.logging_setup")
    @patch("areyouok_telegram.app.database_setup")
    @patch("areyouok_telegram.app.ApplicationBuilder")
    @patch("areyouok_telegram.app.TELEGRAM_BOT_TOKEN", "test_token")
    def test_create_application_configures_telegram_bot(
        self, mock_builder, mock_db_setup, mock_log_setup, mock_set_policy
    ):
        """Test create_application configures Telegram bot with correct token."""
        # Arrange
        mock_application = Mock(spec=Application)
        mock_builder_instance = Mock()
        mock_builder.return_value = mock_builder_instance
        mock_builder_instance.token.return_value = mock_builder_instance
        mock_builder_instance.concurrent_updates.return_value = mock_builder_instance
        mock_builder_instance.post_init.return_value = mock_builder_instance
        mock_builder_instance.build.return_value = mock_application

        # Act
        create_application()

        # Assert
        mock_builder_instance.token.assert_called_once_with("test_token")
        mock_builder_instance.concurrent_updates.assert_called_once_with(concurrent_updates=True)
        mock_builder_instance.post_init.assert_called_once()

    @patch("areyouok_telegram.app.asyncio.set_event_loop_policy")
    @patch("areyouok_telegram.app.logging_setup")
    @patch("areyouok_telegram.app.database_setup")
    @patch("areyouok_telegram.app.ApplicationBuilder")
    def test_create_application_adds_handlers(
        self, mock_builder, mock_db_setup, mock_log_setup, mock_set_policy
    ):
        """Test create_application adds all required handlers."""
        # Arrange
        mock_application = Mock(spec=Application)
        mock_builder_instance = Mock()
        mock_builder.return_value = mock_builder_instance
        mock_builder_instance.token.return_value = mock_builder_instance
        mock_builder_instance.concurrent_updates.return_value = mock_builder_instance
        mock_builder_instance.post_init.return_value = mock_builder_instance
        mock_builder_instance.build.return_value = mock_application

        # Act
        create_application()

        # Assert
        # Should add error handler
        mock_application.add_error_handler.assert_called_once()

        # Should add handlers with correct groups
        assert mock_application.add_handler.call_count == 3
        calls = mock_application.add_handler.call_args_list

        # Check group assignments
        assert calls[0][1]["group"] == 0  # Global update handler
        assert calls[1][1]["group"] == 1  # Message handler
        assert calls[2][1]["group"] == 1  # Edited message handler

    @patch("areyouok_telegram.app.asyncio.set_event_loop_policy")
    @patch("areyouok_telegram.app.logging_setup")
    @patch("areyouok_telegram.app.database_setup")
    @patch("areyouok_telegram.app.ApplicationBuilder")
    def test_create_application_returns_application_instance(
        self, mock_builder, mock_db_setup, mock_log_setup, mock_set_policy
    ):
        """Test create_application returns the built Application instance."""
        # Arrange
        mock_application = Mock(spec=Application)
        mock_builder_instance = Mock()
        mock_builder.return_value = mock_builder_instance
        mock_builder_instance.token.return_value = mock_builder_instance
        mock_builder_instance.concurrent_updates.return_value = mock_builder_instance
        mock_builder_instance.post_init.return_value = mock_builder_instance
        mock_builder_instance.build.return_value = mock_application

        # Act
        result = create_application()

        # Assert
        assert result is mock_application
        assert isinstance(result, type(mock_application))

    @patch("areyouok_telegram.app.asyncio.set_event_loop_policy")
    @patch("areyouok_telegram.app.logging_setup")
    @patch("areyouok_telegram.app.database_setup")
    @patch("areyouok_telegram.app.ApplicationBuilder")
    def test_create_application_setup_order(
        self, mock_builder, mock_db_setup, mock_log_setup, mock_set_policy
    ):
        """Test create_application calls setup functions in correct order."""
        # Arrange
        mock_application = Mock(spec=Application)
        mock_builder_instance = Mock()
        mock_builder.return_value = mock_builder_instance
        mock_builder_instance.token.return_value = mock_builder_instance
        mock_builder_instance.concurrent_updates.return_value = mock_builder_instance
        mock_builder_instance.post_init.return_value = mock_builder_instance
        mock_builder_instance.build.return_value = mock_application

        # Act
        create_application()

        # Assert - Check call order using call_count
        # Event loop policy should be set first
        mock_set_policy.assert_called_once()

        # Then logging and database setup
        mock_log_setup.assert_called_once()
        mock_db_setup.assert_called_once()
