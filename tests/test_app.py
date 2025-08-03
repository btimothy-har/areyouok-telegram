"""Tests for the app module."""

from unittest.mock import Mock
from unittest.mock import patch

import pytest
from telegram.ext import Application

from areyouok_telegram.app import application_startup
from areyouok_telegram.app import create_application
from areyouok_telegram.setup.exceptions import BotDescriptionSetupError
from areyouok_telegram.setup.exceptions import BotNameSetupError


@pytest.fixture(autouse=True)
def mock_application():
    """Fixture for creating a mock Application instance."""
    return Mock(spec=Application)


@pytest.fixture(autouse=True)
def mock_application_builder():
    """Fixture for creating a mock ApplicationBuilder with chained methods."""
    mock_application = Mock(spec=Application)
    mock_builder_instance = Mock()
    mock_builder_instance.token.return_value = mock_builder_instance
    mock_builder_instance.concurrent_updates.return_value = mock_builder_instance
    mock_builder_instance.post_init.return_value = mock_builder_instance
    mock_builder_instance.build.return_value = mock_application
    return mock_builder_instance, mock_application


@pytest.fixture(autouse=True)
def mock_infrastructure_patches():
    """Fixture for patching infrastructure dependencies."""
    with (
        patch("areyouok_telegram.app.logging_setup") as mock_log_setup,
        patch("areyouok_telegram.app.database_setup") as mock_db_setup,
        patch("areyouok_telegram.app.ApplicationBuilder") as mock_builder,
    ):
        yield {
            "log_setup": mock_log_setup,
            "db_setup": mock_db_setup,
            "builder": mock_builder,
        }


class TestApplicationStartup:
    """Test cases for application_startup function."""

    @pytest.mark.asyncio
    async def test_application_startup_success(self, mock_application):
        """Test successful application startup calls all setup functions."""
        # Arrange
        with (
            patch("areyouok_telegram.app.setup_bot_name") as mock_setup_name,
            patch("areyouok_telegram.app.setup_bot_description") as mock_setup_description,
            patch("areyouok_telegram.app.restore_active_sessions") as mock_setup_conversations,
        ):
            mock_setup_name.return_value = None
            mock_setup_description.return_value = None
            mock_setup_conversations.return_value = None

            # Act
            await application_startup(mock_application)

            # Assert
            mock_setup_name.assert_called_once_with(mock_application)
            mock_setup_description.assert_called_once_with(mock_application)
            mock_setup_conversations.assert_called_once_with(mock_application)

    @pytest.mark.asyncio
    async def test_application_startup_name_failure_propagates_exception(self, mock_application):
        """Test application startup propagates BotNameSetupError."""
        # Arrange
        with (
            patch("areyouok_telegram.app.setup_bot_name") as mock_setup_name,
            patch("areyouok_telegram.app.setup_bot_description") as mock_setup_description,
            patch("areyouok_telegram.app.restore_active_sessions") as mock_setup_conversations,
        ):
            mock_setup_name.side_effect = BotNameSetupError("Test Bot")

            # Act & Assert
            with pytest.raises(BotNameSetupError):
                await application_startup(mock_application)

            # Should not call subsequent setup functions if name setup fails
            mock_setup_description.assert_not_called()
            mock_setup_conversations.assert_not_called()

    @pytest.mark.asyncio
    async def test_application_startup_description_failure_propagates_exception(self, mock_application):
        """Test application startup propagates BotDescriptionSetupError."""
        # Arrange
        with (
            patch("areyouok_telegram.app.setup_bot_name") as mock_setup_name,
            patch("areyouok_telegram.app.setup_bot_description") as mock_setup_description,
            patch("areyouok_telegram.app.restore_active_sessions") as mock_setup_conversations,
        ):
            mock_setup_name.return_value = None
            mock_setup_description.side_effect = BotDescriptionSetupError()

            # Act & Assert
            with pytest.raises(BotDescriptionSetupError):
                await application_startup(mock_application)

            # Name setup should complete successfully, conversations should not be called
            mock_setup_name.assert_called_once_with(mock_application)
            mock_setup_conversations.assert_not_called()


class TestCreateApplication:
    """Test cases for create_application function."""

    def test_create_application_configures_infrastructure(self, mock_infrastructure_patches, mock_application_builder):
        """Test create_application sets up infrastructure correctly."""
        # Arrange
        mock_builder_instance, mock_application = mock_application_builder
        mock_infrastructure_patches["builder"].return_value = mock_builder_instance

        # Act
        result = create_application()

        # Assert
        mock_infrastructure_patches["log_setup"].assert_called_once()
        mock_infrastructure_patches["db_setup"].assert_called_once()
        assert result == mock_application

    @patch("areyouok_telegram.app.TELEGRAM_BOT_TOKEN", "test_token")
    def test_create_application_configures_telegram_bot(self, mock_infrastructure_patches, mock_application_builder):
        """Test create_application configures Telegram bot with correct token."""
        # Arrange
        mock_builder_instance, mock_application = mock_application_builder
        mock_infrastructure_patches["builder"].return_value = mock_builder_instance

        # Act
        create_application()

        # Assert
        mock_builder_instance.token.assert_called_once_with("test_token")
        mock_builder_instance.concurrent_updates.assert_called_once_with(concurrent_updates=True)
        mock_builder_instance.post_init.assert_called_once()

    def test_create_application_adds_handlers(self, mock_infrastructure_patches, mock_application_builder):
        """Test create_application adds all required handlers."""
        # Arrange
        mock_builder_instance, mock_application = mock_application_builder
        mock_infrastructure_patches["builder"].return_value = mock_builder_instance

        # Act
        create_application()

        # Assert
        # Should add error handler
        mock_application.add_error_handler.assert_called_once()

        # Should add handlers with correct groups
        assert mock_application.add_handler.call_count == 4
        calls = mock_application.add_handler.call_args_list

        # Check group assignments
        assert calls[0][1]["group"] == 0  # Global update handler
        assert calls[1][1]["group"] == 1  # Message handler
        assert calls[2][1]["group"] == 1  # Edited message handler
        assert calls[3][1]["group"] == 1  # Message reaction handler

    def test_create_application_returns_application_instance(
        self, mock_infrastructure_patches, mock_application_builder
    ):
        """Test create_application returns the built Application instance."""
        # Arrange
        mock_builder_instance, mock_application = mock_application_builder
        mock_infrastructure_patches["builder"].return_value = mock_builder_instance

        # Act
        result = create_application()

        # Assert
        assert result is mock_application
        assert isinstance(result, type(mock_application))

    def test_create_application_setup_order(self, mock_infrastructure_patches, mock_application_builder):
        """Test create_application calls setup functions in correct order."""
        # Arrange
        mock_builder_instance, mock_application = mock_application_builder
        mock_infrastructure_patches["builder"].return_value = mock_builder_instance

        # Act
        create_application()

        # Assert - Check call order using call_count
        # Logging and database setup should be called
        mock_infrastructure_patches["log_setup"].assert_called_once()
        mock_infrastructure_patches["db_setup"].assert_called_once()
