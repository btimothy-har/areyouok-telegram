"""Tests for setup.bot module."""

# ruff: noqa: PLC2701

from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
import telegram

from areyouok_telegram.setup.bot import _generate_bot_name
from areyouok_telegram.setup.bot import _generate_short_description
from areyouok_telegram.setup.bot import package_version
from areyouok_telegram.setup.bot import setup_bot_description
from areyouok_telegram.setup.bot import setup_bot_name
from areyouok_telegram.setup.exceptions import BotDescriptionSetupError
from areyouok_telegram.setup.exceptions import BotNameSetupError


class TestPackageVersion:
    """Test cases for package_version function."""

    def test_package_version_returns_correct_version(self):
        """Test package_version returns the correct package version."""
        # Arrange
        expected_version = "1.0.0"

        with patch("areyouok_telegram.setup.bot.version") as mock_version:
            mock_version.return_value = expected_version

            # Act
            result = package_version()

            # Assert
            assert result == expected_version
            mock_version.assert_called_once_with("areyouok-telegram")


class TestGenerateBotName:
    """Test cases for _generate_bot_name function."""

    @patch("areyouok_telegram.setup.bot.ENV", "production")
    def test_generate_bot_name_production(self):
        """Test bot name generation for production environment."""
        # Act
        result = _generate_bot_name()

        # Assert
        assert result == "Are You OK?"

    @patch("areyouok_telegram.setup.bot.ENV", "development")
    def test_generate_bot_name_development(self):
        """Test bot name generation for development environment."""
        # Act
        result = _generate_bot_name()

        # Assert
        assert result == "Are You OK? [development]"

    @patch("areyouok_telegram.setup.bot.ENV", "staging")
    def test_generate_bot_name_staging(self):
        """Test bot name generation for staging environment."""
        # Act
        result = _generate_bot_name()

        # Assert
        assert result == "Are You OK? [staging]"


class TestGenerateShortDescription:
    """Test cases for _generate_short_description function."""

    @patch("areyouok_telegram.setup.bot.ENV", "production")
    def test_generate_short_description_includes_version(self):
        """Test short description includes version information."""
        with patch("areyouok_telegram.setup.bot.version") as mock_version:
            mock_version.return_value = "2.0.0"

            # Act
            result = _generate_short_description()

            # Assert
            assert "Your empathic companion for everyday life" in result
            assert "[production v2.0.0]" in result

    @patch("areyouok_telegram.setup.bot.ENV", "development")
    def test_generate_short_description_includes_environment(self):
        """Test short description includes environment information."""

        with patch("areyouok_telegram.setup.bot.version") as mock_version:
            mock_version.return_value = "1.5.0"

            # Act
            result = _generate_short_description()

            # Assert
            assert "[development v1.5.0]" in result


class TestSetupBotName:
    """Test cases for setup_bot_name function."""

    @pytest.mark.asyncio
    async def test_setup_bot_name_success(self):
        """Test successful bot name setup."""
        # Arrange
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_application.bot = mock_bot
        mock_bot.get_me.return_value = Mock(first_name="Old Name")
        mock_bot.set_my_name.return_value = True

        # Act
        await setup_bot_name(mock_application)

        # Assert
        mock_bot.get_me.assert_called_once()
        mock_bot.set_my_name.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_bot_name_skips_if_already_set(self):
        """Test bot name setup skips if name is already correct."""
        # Arrange
        expected_name = "Are You OK? [test]"
        with patch("areyouok_telegram.setup.bot._generate_bot_name") as mock_generate_name:
            mock_generate_name.return_value = expected_name
            mock_application = Mock()
            mock_bot = AsyncMock()
            mock_application.bot = mock_bot
            mock_bot.get_me.return_value = Mock(first_name=expected_name)

            # Act
            await setup_bot_name(mock_application)

            # Assert
            mock_bot.get_me.assert_called_once()
            mock_bot.set_my_name.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_bot_name_failure_raises_exception(self):
        """Test bot name setup failure raises BotNameSetupError."""
        # Arrange
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_application.bot = mock_bot
        mock_bot.get_me.return_value = Mock(first_name="Old Name")
        mock_bot.set_my_name.return_value = False

        # Act & Assert
        with pytest.raises(BotNameSetupError):
            await setup_bot_name(mock_application)

    @pytest.mark.asyncio
    async def test_setup_bot_name_uses_generated_name(self):
        """Test setup_bot_name uses the generated name."""
        # Arrange
        expected_name = "Test Bot Name"

        with patch("areyouok_telegram.setup.bot._generate_bot_name") as mock_generate_name:
            mock_generate_name.return_value = expected_name
            mock_application = Mock()
            mock_bot = AsyncMock()
            mock_application.bot = mock_bot
            mock_bot.get_me.return_value = Mock(first_name="Old Name")
            mock_bot.set_my_name.return_value = True

            # Act
            await setup_bot_name(mock_application)

            # Assert
            mock_bot.set_my_name.assert_called_once_with(name=expected_name)

    @pytest.mark.asyncio
    async def test_setup_bot_name_handles_rate_limit(self):
        """Test setup_bot_name handles RetryAfter exception with job queue retry."""
        # Arrange
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_job_queue = Mock()
        mock_application.bot = mock_bot
        mock_application.job_queue = mock_job_queue
        mock_bot.get_me.return_value = Mock(first_name="Old Name")

        retry_after_seconds = 30
        retry_after_error = telegram.error.RetryAfter(retry_after_seconds)
        mock_bot.set_my_name.side_effect = retry_after_error

        # Act
        await setup_bot_name(mock_application)

        # Assert
        mock_bot.set_my_name.assert_called_once()
        mock_job_queue.run_once.assert_called_once()

        # Verify job queue call parameters
        call_args = mock_job_queue.run_once.call_args
        assert call_args[1]["callback"] == setup_bot_name
        assert call_args[1]["when"] == timedelta(seconds=retry_after_seconds + 60)  # retry_after + 60
        assert call_args[1]["name"] == "retry_set_bot_name"

    @pytest.mark.asyncio
    async def test_setup_bot_name_handles_rate_limit_with_timedelta(self):
        """Test setup_bot_name handles RetryAfter exception with timedelta retry_after."""
        # Arrange
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_job_queue = Mock()
        mock_application.bot = mock_bot
        mock_application.job_queue = mock_job_queue
        mock_bot.get_me.return_value = Mock(first_name="Old Name")

        retry_after_delta = timedelta(seconds=45)
        retry_after_error = telegram.error.RetryAfter(retry_after_delta)
        mock_bot.set_my_name.side_effect = retry_after_error

        # Act
        await setup_bot_name(mock_application)

        # Assert
        mock_bot.set_my_name.assert_called_once()
        mock_job_queue.run_once.assert_called_once()

        # Verify job queue call parameters
        call_args = mock_job_queue.run_once.call_args
        assert call_args[1]["callback"] == setup_bot_name
        assert call_args[1]["when"] == retry_after_delta + timedelta(seconds=60)  # retry_after + 60
        assert call_args[1]["name"] == "retry_set_bot_name"


class TestSetupBotDescription:
    """Test cases for setup_bot_description function."""

    @pytest.mark.asyncio
    async def test_setup_bot_description_success(self):
        """Test successful bot description setup."""
        # Arrange
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_application.bot = mock_bot
        mock_bot.get_my_short_description.return_value = Mock(short_description="Old Description")
        mock_bot.set_my_description.return_value = True
        mock_bot.set_my_short_description.return_value = True

        # Act
        await setup_bot_description(mock_application)

        # Assert
        mock_bot.get_my_short_description.assert_called_once()
        mock_bot.set_my_description.assert_called_once()
        mock_bot.set_my_short_description.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_bot_description_skips_if_already_set(self):
        """Test bot description setup skips if description is already correct."""
        # Arrange
        expected_description = "Test description"
        with patch("areyouok_telegram.setup.bot._generate_short_description") as mock_generate_desc:
            mock_generate_desc.return_value = expected_description
            mock_application = Mock()
            mock_bot = AsyncMock()
            mock_application.bot = mock_bot
            mock_bot.get_my_short_description.return_value = Mock(short_description=expected_description)

            # Act
            await setup_bot_description(mock_application)

            # Assert
            mock_bot.get_my_short_description.assert_called_once()
            mock_bot.set_my_description.assert_not_called()
            mock_bot.set_my_short_description.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_bot_description_failure_raises_exception(self):
        """Test bot description setup failure raises BotDescriptionSetupError."""
        # Arrange
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_application.bot = mock_bot
        mock_bot.get_my_short_description.return_value = Mock(short_description="Old Description")
        mock_bot.set_my_description.return_value = True
        mock_bot.set_my_short_description.return_value = False

        # Act & Assert
        with pytest.raises(BotDescriptionSetupError):
            await setup_bot_description(mock_application)

    @pytest.mark.asyncio
    async def test_setup_bot_description_uses_generated_description(self):
        """Test setup_bot_description uses the generated description."""
        # Arrange
        expected_description = "Test bot description"

        with patch("areyouok_telegram.setup.bot._generate_short_description") as mock_generate_desc:
            mock_generate_desc.return_value = expected_description
            mock_application = Mock()
            mock_bot = AsyncMock()
            mock_application.bot = mock_bot
            mock_bot.get_my_short_description.return_value = Mock(short_description="Old Description")
            mock_bot.set_my_description.return_value = True
            mock_bot.set_my_short_description.return_value = True

            # Act
            await setup_bot_description(mock_application)

            # Assert
            mock_bot.set_my_description.assert_called_once_with(description=expected_description)
            mock_bot.set_my_short_description.assert_called_once_with(short_description=expected_description)

    @pytest.mark.asyncio
    async def test_setup_bot_description_handles_rate_limit(self):
        """Test setup_bot_description handles RetryAfter exception with job queue retry."""
        # Arrange
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_job_queue = Mock()
        mock_application.bot = mock_bot
        mock_application.job_queue = mock_job_queue
        mock_bot.get_my_short_description.return_value = Mock(short_description="Old Description")

        retry_after_seconds = 45
        retry_after_error = telegram.error.RetryAfter(retry_after_seconds)
        mock_bot.set_my_description.side_effect = retry_after_error

        # Act
        await setup_bot_description(mock_application)

        # Assert
        mock_bot.set_my_description.assert_called_once()
        mock_job_queue.run_once.assert_called_once()

        # Verify job queue call parameters
        call_args = mock_job_queue.run_once.call_args
        assert call_args[1]["callback"] == setup_bot_description
        assert call_args[1]["when"] == timedelta(seconds=retry_after_seconds + 60)  # retry_after + 60
        assert call_args[1]["name"] == "retry_set_bot_description"

    @pytest.mark.asyncio
    async def test_setup_bot_description_handles_rate_limit_with_timedelta(self):
        """Test setup_bot_description handles RetryAfter exception with timedelta retry_after."""
        # Arrange
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_job_queue = Mock()
        mock_application.bot = mock_bot
        mock_application.job_queue = mock_job_queue
        mock_bot.get_my_short_description.return_value = Mock(short_description="Old Description")

        retry_after_delta = timedelta(seconds=120)
        retry_after_error = telegram.error.RetryAfter(retry_after_delta)
        mock_bot.set_my_description.side_effect = retry_after_error

        # Act
        await setup_bot_description(mock_application)

        # Assert
        mock_bot.set_my_description.assert_called_once()
        mock_job_queue.run_once.assert_called_once()

        # Verify job queue call parameters
        call_args = mock_job_queue.run_once.call_args
        assert call_args[1]["callback"] == setup_bot_description
        assert call_args[1]["when"] == retry_after_delta + timedelta(seconds=60)  # retry_after + 60
        assert call_args[1]["name"] == "retry_set_bot_description"
