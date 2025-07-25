"""Tests for setup.bot module."""

from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from areyouok_telegram.setup.bot import _generate_bot_name
from areyouok_telegram.setup.bot import _generate_short_description
from areyouok_telegram.setup.bot import package_version
from areyouok_telegram.setup.bot import setup_bot_description
from areyouok_telegram.setup.bot import setup_bot_name
from areyouok_telegram.setup.exceptions import BotDescriptionSetupError
from areyouok_telegram.setup.exceptions import BotNameSetupError


class TestPackageVersion:
    """Test cases for package_version function."""

    @patch("areyouok_telegram.setup.bot.version")
    def test_package_version_returns_correct_version(self, mock_version):
        """Test package_version returns the correct package version."""
        # Arrange
        expected_version = "1.0.0"
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
    @patch("areyouok_telegram.setup.bot.version")
    def test_generate_short_description_includes_version(self, mock_version):
        """Test short description includes version information."""
        # Arrange
        mock_version.return_value = "2.0.0"

        # Act
        result = _generate_short_description()

        # Assert
        assert "Your empathic companion for everyday life" in result
        assert "[production v2.0.0]" in result

    @patch("areyouok_telegram.setup.bot.ENV", "development")
    @patch("areyouok_telegram.setup.bot.version")
    def test_generate_short_description_includes_environment(self, mock_version):
        """Test short description includes environment information."""
        # Arrange
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
        mock_bot.set_my_name.return_value = True

        # Act
        await setup_bot_name(mock_application)

        # Assert
        mock_bot.set_my_name.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_bot_name_failure_raises_exception(self):
        """Test bot name setup failure raises BotNameSetupError."""
        # Arrange
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_application.bot = mock_bot
        mock_bot.set_my_name.return_value = False

        # Act & Assert
        with pytest.raises(BotNameSetupError):
            await setup_bot_name(mock_application)

    @pytest.mark.asyncio
    @patch("areyouok_telegram.setup.bot._generate_bot_name")
    async def test_setup_bot_name_uses_generated_name(self, mock_generate_name):
        """Test setup_bot_name uses the generated name."""
        # Arrange
        expected_name = "Test Bot Name"
        mock_generate_name.return_value = expected_name
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_application.bot = mock_bot
        mock_bot.set_my_name.return_value = True

        # Act
        await setup_bot_name(mock_application)

        # Assert
        mock_bot.set_my_name.assert_called_once_with(name=expected_name)


class TestSetupBotDescription:
    """Test cases for setup_bot_description function."""

    @pytest.mark.asyncio
    async def test_setup_bot_description_success(self):
        """Test successful bot description setup."""
        # Arrange
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_application.bot = mock_bot
        mock_bot.set_my_short_description.return_value = True

        # Act
        await setup_bot_description(mock_application)

        # Assert
        mock_bot.set_my_short_description.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_bot_description_failure_raises_exception(self):
        """Test bot description setup failure raises BotDescriptionSetupError."""
        # Arrange
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_application.bot = mock_bot
        mock_bot.set_my_short_description.return_value = False

        # Act & Assert
        with pytest.raises(BotDescriptionSetupError):
            await setup_bot_description(mock_application)

    @pytest.mark.asyncio
    @patch("areyouok_telegram.setup.bot._generate_short_description")
    async def test_setup_bot_description_uses_generated_description(self, mock_generate_desc):
        """Test setup_bot_description uses the generated description."""
        # Arrange
        expected_description = "Test bot description"
        mock_generate_desc.return_value = expected_description
        mock_application = Mock()
        mock_bot = AsyncMock()
        mock_application.bot = mock_bot
        mock_bot.set_my_short_description.return_value = True

        # Act
        await setup_bot_description(mock_application)

        # Assert
        mock_bot.set_my_short_description.assert_called_once_with(short_description=expected_description)
