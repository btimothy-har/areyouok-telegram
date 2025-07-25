"""Tests for setup.logging module."""

import logging
from unittest.mock import patch

from areyouok_telegram.setup.logging import logging_setup




class TestLoggingSetup:
    """Test cases for logging_setup function."""

    @patch("areyouok_telegram.setup.logging.logfire")
    @patch("areyouok_telegram.setup.logging.logging")
    def test_logging_setup_basic_configuration(self, mock_logging, mock_logfire):
        """Test logging setup configures basic logging with Logfire handler."""
        # Act
        logging_setup()

        # Assert
        mock_logging.basicConfig.assert_called_once_with(
            level=logging.INFO, handlers=[mock_logfire.LogfireLoggingHandler()]
        )

    @patch("areyouok_telegram.setup.logging.logfire")
    @patch("areyouok_telegram.setup.logging.logging")
    def test_logging_setup_configures_third_party_loggers(self, mock_logging, mock_logfire):
        """Test logging setup sets appropriate levels for third-party loggers."""
        # Act
        logging_setup()

        # Assert
        mock_logging.getLogger.assert_any_call("httpx")
        mock_logging.getLogger.assert_any_call("apscheduler.scheduler")
        mock_logging.getLogger.assert_any_call("apscheduler.executors.default")

    @patch("areyouok_telegram.setup.logging.ENV", "production")
    @patch("areyouok_telegram.setup.logging.GITHUB_REPOSITORY", "user/repo")
    @patch("areyouok_telegram.setup.logging.GITHUB_SHA", "abc123")
    @patch("areyouok_telegram.setup.logging.LOGFIRE_TOKEN", "test_token")
    @patch("areyouok_telegram.setup.logging.logfire")
    def test_logging_setup_production_environment(self, mock_logfire):
        """Test logging setup for production environment with GitHub integration."""
        # Act
        logging_setup()

        # Assert
        mock_logfire.CodeSource.assert_called_once_with(
            repository="https://github.com/user/repo",
            revision="abc123",
        )
        mock_logfire.configure.assert_called_once()

    @patch("areyouok_telegram.setup.logging.ENV", "development")
    @patch("areyouok_telegram.setup.logging.LOGFIRE_TOKEN", "test_token")
    @patch("areyouok_telegram.setup.logging.logfire")
    def test_logging_setup_development_environment(self, mock_logfire):
        """Test logging setup for development environment with console output."""
        # Act
        logging_setup()

        # Assert
        mock_logfire.ConsoleOptions.assert_called_once_with(
            span_style="show-parents",
            show_project_link=False,
        )

    @patch("areyouok_telegram.setup.logging.LOGFIRE_TOKEN", None)
    @patch("areyouok_telegram.setup.logging.logfire")
    def test_logging_setup_without_logfire_token(self, mock_logfire):
        """Test logging setup when LOGFIRE_TOKEN is not provided."""
        # Act
        logging_setup()

        # Assert
        # Verify logfire.configure is called with send_to_logfire=False
        args, kwargs = mock_logfire.configure.call_args
        assert kwargs["send_to_logfire"] is False

    @patch("areyouok_telegram.setup.logging.ENV", "staging")
    @patch("areyouok_telegram.setup.logging.GITHUB_REPOSITORY", None)
    @patch("areyouok_telegram.setup.logging.logfire")
    def test_logging_setup_staging_without_github_info(self, mock_logfire):
        """Test logging setup in staging environment without GitHub repository info."""
        # Act
        logging_setup()

        # Assert
        # Should not create CodeSource when GITHUB_REPOSITORY is None
        mock_logfire.CodeSource.assert_not_called()

    @patch("areyouok_telegram.setup.logging.logfire")
    @patch("areyouok_telegram.setup.logging.version")
    def test_logging_setup_includes_service_version(self, mock_version, mock_logfire):
        """Test logging setup includes the correct service version."""
        # Arrange
        expected_version = "2.0.0"
        mock_version.return_value = expected_version

        # Act
        logging_setup()

        # Assert
        args, kwargs = mock_logfire.configure.call_args
        assert kwargs["service_version"] == expected_version
