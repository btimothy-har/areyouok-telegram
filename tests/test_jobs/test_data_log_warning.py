"""Tests for jobs/data_log_warning.py."""

import hashlib
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from telegram.ext import ContextTypes

from areyouok_telegram.jobs.data_log_warning import DataLogWarningJob


class TestDataLogWarningJob:
    """Test the DataLogWarningJob class."""

    def test_init(self):
        """Test DataLogWarningJob initialization."""
        job = DataLogWarningJob()

        # Should inherit from BaseJob
        assert job._bot_id is None
        assert job._run_count == 0
        assert job._run_timestamp is not None

    def test_name_property(self):
        """Test name property returns correct job name."""
        job = DataLogWarningJob()
        assert job.name == "data_log_warning"

    def test_id_property(self):
        """Test job ID is consistent MD5 hash of name."""
        job = DataLogWarningJob()

        # ID should be MD5 hash of name
        expected_id = hashlib.md5(b"data_log_warning").hexdigest()
        assert job.id == expected_id

    @pytest.mark.asyncio
    async def test_run_log_chat_messages_true_env_controlled(self):
        """Test warning logged when LOG_CHAT_MESSAGES is True and ENV is controlled."""
        job = DataLogWarningJob()
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"

        with (
            patch("areyouok_telegram.jobs.data_log_warning.LOG_CHAT_MESSAGES", new=True),
            patch("areyouok_telegram.jobs.data_log_warning.ENV", "staging"),
            patch("areyouok_telegram.jobs.data_log_warning.CONTROLLED_ENV", ["staging", "production"]),
            patch("areyouok_telegram.jobs.data_log_warning.USER_ENCRYPTION_SALT", "secure-salt"),
            patch("areyouok_telegram.jobs.data_log_warning.logfire.warning") as mock_warning,
        ):
            await job._run(mock_context)

            # Should log warning about chat messages
            mock_warning.assert_called_once_with(
                "Logging chat messages in a controlled environment. "
                "This may expose sensitive user data. Ensure this is intentional."
            )

    @pytest.mark.asyncio
    async def test_run_log_chat_messages_false_env_controlled(self):
        """Test no warning when LOG_CHAT_MESSAGES is False but ENV is controlled."""
        job = DataLogWarningJob()
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"

        with (
            patch("areyouok_telegram.jobs.data_log_warning.LOG_CHAT_MESSAGES", new=False),
            patch("areyouok_telegram.jobs.data_log_warning.ENV", "staging"),
            patch("areyouok_telegram.jobs.data_log_warning.CONTROLLED_ENV", ["staging", "production"]),
            patch("areyouok_telegram.jobs.data_log_warning.USER_ENCRYPTION_SALT", "secure-salt"),
            patch("areyouok_telegram.jobs.data_log_warning.logfire.warning") as mock_warning,
        ):
            await job._run(mock_context)

            # Should not log any warning
            mock_warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_log_chat_messages_true_env_not_controlled(self):
        """Test no warning when LOG_CHAT_MESSAGES is True but ENV is not controlled."""
        job = DataLogWarningJob()
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"

        with (
            patch("areyouok_telegram.jobs.data_log_warning.LOG_CHAT_MESSAGES", new=True),
            patch("areyouok_telegram.jobs.data_log_warning.ENV", "development"),
            patch("areyouok_telegram.jobs.data_log_warning.CONTROLLED_ENV", ["staging", "production"]),
            patch("areyouok_telegram.jobs.data_log_warning.USER_ENCRYPTION_SALT", "secure-salt"),
            patch("areyouok_telegram.jobs.data_log_warning.logfire.warning") as mock_warning,
        ):
            await job._run(mock_context)

            # Should not log any warning
            mock_warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_encryption_salt_default_env_controlled(self):
        """Test warning logged when USER_ENCRYPTION_SALT is default and ENV is controlled."""
        job = DataLogWarningJob()
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"

        with (
            patch("areyouok_telegram.jobs.data_log_warning.LOG_CHAT_MESSAGES", new=False),
            patch("areyouok_telegram.jobs.data_log_warning.ENV", "production"),
            patch("areyouok_telegram.jobs.data_log_warning.CONTROLLED_ENV", ["staging", "production"]),
            patch("areyouok_telegram.jobs.data_log_warning.USER_ENCRYPTION_SALT", "default-salt"),
            patch("areyouok_telegram.jobs.data_log_warning.logfire.warning") as mock_warning,
        ):
            await job._run(mock_context)

            # Should log warning about encryption salt
            mock_warning.assert_called_once_with(
                "USER_ENCRYPTION_SALT is set to the default value. "
                "This should be changed in production to ensure user data security."
            )

    @pytest.mark.asyncio
    async def test_run_encryption_salt_secure_env_controlled(self):
        """Test no warning when USER_ENCRYPTION_SALT is secure and ENV is controlled."""
        job = DataLogWarningJob()
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"

        with (
            patch("areyouok_telegram.jobs.data_log_warning.LOG_CHAT_MESSAGES", new=False),
            patch("areyouok_telegram.jobs.data_log_warning.ENV", "production"),
            patch("areyouok_telegram.jobs.data_log_warning.CONTROLLED_ENV", ["staging", "production"]),
            patch("areyouok_telegram.jobs.data_log_warning.USER_ENCRYPTION_SALT", "secure-random-salt"),
            patch("areyouok_telegram.jobs.data_log_warning.logfire.warning") as mock_warning,
        ):
            await job._run(mock_context)

            # Should not log any warning
            mock_warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_encryption_salt_default_env_not_controlled(self):
        """Test no warning when USER_ENCRYPTION_SALT is default but ENV is not controlled."""
        job = DataLogWarningJob()
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"

        with (
            patch("areyouok_telegram.jobs.data_log_warning.LOG_CHAT_MESSAGES", new=False),
            patch("areyouok_telegram.jobs.data_log_warning.ENV", "development"),
            patch("areyouok_telegram.jobs.data_log_warning.CONTROLLED_ENV", ["staging", "production"]),
            patch("areyouok_telegram.jobs.data_log_warning.USER_ENCRYPTION_SALT", "default-salt"),
            patch("areyouok_telegram.jobs.data_log_warning.logfire.warning") as mock_warning,
        ):
            await job._run(mock_context)

            # Should not log any warning
            mock_warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_both_conditions_true(self):
        """Test both warnings logged when both conditions are met."""
        job = DataLogWarningJob()
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"

        with (
            patch("areyouok_telegram.jobs.data_log_warning.LOG_CHAT_MESSAGES", new=True),
            patch("areyouok_telegram.jobs.data_log_warning.ENV", "staging"),
            patch("areyouok_telegram.jobs.data_log_warning.CONTROLLED_ENV", ["staging", "production"]),
            patch("areyouok_telegram.jobs.data_log_warning.USER_ENCRYPTION_SALT", "default-salt"),
            patch("areyouok_telegram.jobs.data_log_warning.logfire.warning") as mock_warning,
        ):
            await job._run(mock_context)

            # Should log both warnings
            assert mock_warning.call_count == 2
            mock_warning.assert_any_call(
                "Logging chat messages in a controlled environment. "
                "This may expose sensitive user data. Ensure this is intentional."
            )
            mock_warning.assert_any_call(
                "USER_ENCRYPTION_SALT is set to the default value. "
                "This should be changed in production to ensure user data security."
            )

    @pytest.mark.asyncio
    async def test_run_no_warnings_development_env(self):
        """Test no warnings in development environment regardless of other settings."""
        job = DataLogWarningJob()
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"

        with (
            patch("areyouok_telegram.jobs.data_log_warning.LOG_CHAT_MESSAGES", new=True),
            patch("areyouok_telegram.jobs.data_log_warning.ENV", "development"),
            patch("areyouok_telegram.jobs.data_log_warning.CONTROLLED_ENV", ["staging", "production"]),
            patch("areyouok_telegram.jobs.data_log_warning.USER_ENCRYPTION_SALT", "default-salt"),
            patch("areyouok_telegram.jobs.data_log_warning.logfire.warning") as mock_warning,
        ):
            await job._run(mock_context)

            # Should not log any warning in development
            mock_warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_controlled_env_variations(self):
        """Test with different controlled environment values."""
        job = DataLogWarningJob()
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"

        # Test with 'staging' environment from CONTROLLED_ENV
        with (
            patch("areyouok_telegram.jobs.data_log_warning.LOG_CHAT_MESSAGES", new=True),
            patch("areyouok_telegram.jobs.data_log_warning.ENV", "staging"),
            patch("areyouok_telegram.jobs.data_log_warning.CONTROLLED_ENV", ["staging", "production"]),
            patch("areyouok_telegram.jobs.data_log_warning.USER_ENCRYPTION_SALT", "secure-salt"),
            patch("areyouok_telegram.jobs.data_log_warning.logfire.warning") as mock_warning,
        ):
            await job._run(mock_context)

            # Should log warning about chat messages
            mock_warning.assert_called_once_with(
                "Logging chat messages in a controlled environment. "
                "This may expose sensitive user data. Ensure this is intentional."
            )
