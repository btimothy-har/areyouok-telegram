"""Tests for setup.logging module."""

from unittest.mock import patch

import pytest

from areyouok_telegram.setup import logging_setup


@pytest.fixture(autouse=True)
def mock_logging():
    """Fixture for mocking logging module."""
    with patch("areyouok_telegram.setup.logging.logging") as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_logfire():
    """Fixture for mocking logfire module."""
    with patch("areyouok_telegram.setup.logging.logfire") as mock:
        yield mock


class TestLoggingSetup:
    """Test cases for logging_setup function."""

    def test_logging_setup_basic_configuration(self, mock_logging, mock_logfire):
        """Test logging setup configures basic logging with Logfire handler."""
        # Act
        logging_setup()

        # Assert
        # Check that the root logger gets the handler
        mock_logging.getLogger.assert_any_call()
        # Get the mock for the root logger
        root_logger = mock_logging.getLogger.return_value
        root_logger.addHandler.assert_called_once_with(mock_logfire.LogfireLoggingHandler.return_value)

    def test_logging_setup_configures_third_party_loggers(self, mock_logging):
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
        mock_logfire.log_slow_async_callbacks.assert_called_once_with(slow_duration=0.25)

    @patch("areyouok_telegram.setup.logging.ENV", "development")
    @patch("areyouok_telegram.setup.logging.LOGFIRE_TOKEN", "test_token")
    def test_logging_setup_development_environment(self, mock_logfire):
        """Test logging setup for development environment with console output."""
        # Act
        logging_setup()

        # Assert
        mock_logfire.ConsoleOptions.assert_called_once_with(
            span_style="show-parents",
            show_project_link=False,
            min_log_level="debug",
            verbose=True,
        )
        mock_logfire.log_slow_async_callbacks.assert_called_once_with(slow_duration=0.25)

    @patch("areyouok_telegram.setup.logging.LOGFIRE_TOKEN", None)
    def test_logging_setup_without_logfire_token(self, mock_logfire):
        """Test logging setup when LOGFIRE_TOKEN is not provided."""
        # Act
        logging_setup()

        # Assert
        # Verify logfire.configure is called with send_to_logfire=False
        _, kwargs = mock_logfire.configure.call_args
        assert kwargs["send_to_logfire"] is False
        mock_logfire.log_slow_async_callbacks.assert_called_once_with(slow_duration=0.25)

    @patch("areyouok_telegram.setup.logging.ENV", "staging")
    @patch("areyouok_telegram.setup.logging.GITHUB_REPOSITORY", None)
    def test_logging_setup_staging_without_github_info(self, mock_logfire):
        """Test logging setup in staging environment without GitHub repository info."""
        # Act
        logging_setup()

        # Assert
        # Should not create CodeSource when GITHUB_REPOSITORY is None
        mock_logfire.CodeSource.assert_not_called()
        mock_logfire.log_slow_async_callbacks.assert_called_once_with(slow_duration=0.25)

    def test_logging_setup_includes_service_version(self, mock_logfire):
        """Test logging setup includes the correct service version."""

        expected_version = "2.0.0"
        with patch("areyouok_telegram.setup.logging.version") as mock_version:
            mock_version.return_value = expected_version

            # Act
            logging_setup()

            # Assert
            _, kwargs = mock_logfire.configure.call_args
            assert kwargs["service_version"] == expected_version
            mock_logfire.log_slow_async_callbacks.assert_called_once_with(slow_duration=0.25)

    @patch("areyouok_telegram.setup.logging.ENV", "test")
    @patch("areyouok_telegram.setup.logging.LOGFIRE_TOKEN", "test_token")
    def test_logging_setup_non_development_environment(self, mock_logfire):
        """Test logging setup for non-development environment with console output."""
        # Act
        logging_setup()

        # Assert
        mock_logfire.ConsoleOptions.assert_called_once_with(
            span_style="show-parents",
            show_project_link=False,
            min_log_level="info",
            verbose=True,
        )
        mock_logfire.log_slow_async_callbacks.assert_called_once_with(slow_duration=0.25)
