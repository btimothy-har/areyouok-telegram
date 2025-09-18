"""Test module for LLM models base configuration."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pydantic_ai
import pytest
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from areyouok_telegram.llms.exceptions import ModelConfigurationError
from areyouok_telegram.llms.models import BaseModelConfig


@pytest.fixture(autouse=True)
def disable_frozen_time():
    """Disable the frozen time fixture for model tests to avoid pydantic conflicts."""
    yield


class TestBaseModelConfig:
    """Test the BaseModelConfig class."""

    def test_init_with_model_id(self):
        """Test successful initialization with model_id."""
        config = BaseModelConfig(
            model_id="gpt-4",
            provider="openai",
        )

        assert config.provider == "openai"
        assert config.model_id == "gpt-4"
        assert config.openrouter_id is None
        assert config.model_settings is None

    def test_init_with_openrouter_id(self):
        """Test successful initialization with openrouter_id."""
        config = BaseModelConfig(
            model_id="claude-3-sonnet-20241022",
            provider="anthropic",
            openrouter_id="anthropic/claude-3-sonnet",
        )

        assert config.provider == "anthropic"
        assert config.model_id == "claude-3-sonnet-20241022"
        assert config.openrouter_id == "anthropic/claude-3-sonnet"
        assert config.model_settings is None

    def test_init_with_both_ids(self):
        """Test successful initialization with both model_id and openrouter_id."""
        model_settings = MagicMock(spec=pydantic_ai.settings.ModelSettings)

        config = BaseModelConfig(
            model_id="gpt-4",
            provider="openai",
            openrouter_id="openai/gpt-4",
            model_settings=model_settings,
        )

        assert config.provider == "openai"
        assert config.model_id == "gpt-4"
        assert config.openrouter_id == "openai/gpt-4"
        assert config.model_settings == model_settings

    @patch("areyouok_telegram.llms.models.ANTHROPIC_API_KEY", "test-anthropic-key")
    def test_primary_model_anthropic_with_api_key(self):
        """Test primary_model returns AnthropicModel when provider is anthropic and API key exists."""
        model_settings = MagicMock(spec=pydantic_ai.settings.ModelSettings)

        config = BaseModelConfig(
            model_id="claude-3-sonnet-20241022",
            provider="anthropic",
            model_settings=model_settings,
        )

        with patch("areyouok_telegram.llms.models.AnthropicModel") as mock_anthropic:
            mock_model = MagicMock(spec=AnthropicModel)
            mock_anthropic.return_value = mock_model

            result = config.primary_model

            mock_anthropic.assert_called_once_with(
                model_name="claude-3-sonnet-20241022",
                settings=model_settings,
            )
            assert result == mock_model

    @patch("areyouok_telegram.llms.models.OPENAI_API_KEY", "test-openai-key")
    def test_primary_model_openai_with_api_key(self):
        """Test primary_model returns OpenAIModel when provider is openai and API key exists."""
        model_settings = MagicMock(spec=pydantic_ai.settings.ModelSettings)

        config = BaseModelConfig(
            model_id="gpt-4",
            provider="openai",
            model_settings=model_settings,
        )

        with patch("areyouok_telegram.llms.models.OpenAIModel") as mock_openai:
            mock_model = MagicMock(spec=OpenAIModel)
            mock_openai.return_value = mock_model

            result = config.primary_model

            mock_openai.assert_called_once_with(
                model_name="gpt-4",
                settings=model_settings,
            )
            assert result == mock_model

    @patch("areyouok_telegram.llms.models.ANTHROPIC_API_KEY", None)
    def test_primary_model_returns_none_when_anthropic_no_api_key(self):
        """Test primary_model returns None when provider is anthropic but no API key exists."""
        # This tests line 66: return None
        config = BaseModelConfig(
            model_id="claude-3-sonnet-20241022",
            provider="anthropic",
        )

        result = config.primary_model
        assert result is None

    @patch("areyouok_telegram.llms.models.OPENAI_API_KEY", None)
    def test_primary_model_returns_none_when_openai_no_api_key(self):
        """Test primary_model returns None when provider is openai but no API key exists."""
        # This tests line 66: return None
        config = BaseModelConfig(
            model_id="gpt-4",
            provider="openai",
        )

        result = config.primary_model
        assert result is None

    @patch("areyouok_telegram.llms.models.OPENROUTER_API_KEY", "test-openrouter-key")
    def test_openrouter_model_with_api_key_and_id(self):
        """Test openrouter_model returns OpenAIModel when openrouter_id and API key exist."""
        model_settings = MagicMock(spec=pydantic_ai.settings.ModelSettings)

        config = BaseModelConfig(
            model_id="gpt-4",
            provider="openai",
            openrouter_id="openai/gpt-4-turbo",
            model_settings=model_settings,
        )

        with (
            patch("areyouok_telegram.llms.models.OpenAIModel") as mock_openai,
            patch("areyouok_telegram.llms.models.OpenRouterProvider") as mock_provider,
        ):
            mock_model = MagicMock(spec=OpenAIModel)
            mock_openai.return_value = mock_model
            mock_provider_instance = MagicMock(spec=OpenRouterProvider)
            mock_provider.return_value = mock_provider_instance

            result = config.openrouter_model

            mock_provider.assert_called_once_with(api_key="test-openrouter-key")
            mock_openai.assert_called_once_with(
                model_name="openai/gpt-4-turbo",
                provider=mock_provider_instance,
                settings=model_settings,
            )
            assert result == mock_model

    @patch("areyouok_telegram.llms.models.OPENROUTER_API_KEY", None)
    def test_openrouter_model_returns_none_when_no_api_key(self):
        """Test openrouter_model returns None when no OpenRouter API key exists."""
        # This tests line 77: return None
        config = BaseModelConfig(
            model_id="gpt-4",
            provider="openai",
            openrouter_id="openai/gpt-4-turbo",
        )

        result = config.openrouter_model
        assert result is None

    @patch("areyouok_telegram.llms.models.OPENROUTER_API_KEY", "test-openrouter-key")
    def test_openrouter_model_returns_none_when_no_openrouter_id(self):
        """Test openrouter_model returns None when no openrouter_id is provided."""
        # This tests line 77: return None
        config = BaseModelConfig(
            model_id="gpt-4",
            provider="openai",
            # openrouter_id is None
        )

        result = config.openrouter_model
        assert result is None

    @patch("areyouok_telegram.llms.models.OPENAI_API_KEY", "test-openai-key")
    @patch("areyouok_telegram.llms.models.OPENROUTER_API_KEY", "test-openrouter-key")
    def test_model_property_returns_fallback_model_when_both_models_available(self):
        """Test model property returns FallbackModel when both primary and openrouter models are available."""
        config = BaseModelConfig(
            model_id="gpt-4",
            provider="openai",
            openrouter_id="openai/gpt-4-turbo",
        )

        mock_primary = MagicMock(spec=pydantic_ai.models.Model)
        mock_openrouter = MagicMock(spec=pydantic_ai.models.Model)

        with (
            patch("areyouok_telegram.llms.models.OpenAIModel") as mock_openai_cls,
            patch("areyouok_telegram.llms.models.OpenRouterProvider") as mock_provider_cls,
            patch("areyouok_telegram.llms.models.FallbackModel") as mock_fallback,
            patch("areyouok_telegram.llms.models.should_retry_llm_error") as mock_retry_func,
        ):
            # Set up calls: first call for primary model, second call for openrouter model
            def openai_side_effect(*_args, **kwargs):
                if "provider" in kwargs:
                    # This is the openrouter model call (has provider argument)
                    return mock_openrouter
                else:
                    # This is the primary model call (no provider argument)
                    return mock_primary

            mock_openai_cls.side_effect = openai_side_effect
            mock_provider_cls.return_value = MagicMock(spec=OpenRouterProvider)

            mock_fallback_model = MagicMock(spec=FallbackModel)
            mock_fallback.return_value = mock_fallback_model

            result = config.model

            mock_fallback.assert_called_once_with(
                mock_primary,
                mock_openrouter,
                fallback_on=mock_retry_func,
            )
            assert result == mock_fallback_model

    @patch("areyouok_telegram.llms.models.OPENAI_API_KEY", "test-openai-key")
    @patch("areyouok_telegram.llms.models.OPENROUTER_API_KEY", None)
    def test_model_property_returns_primary_model_only(self):
        """Test model property returns primary model when only primary model is available."""
        # This tests lines 46-47: elif self.primary_model: return self.primary_model
        config = BaseModelConfig(
            model_id="gpt-4",
            provider="openai",
        )

        mock_primary = MagicMock(spec=pydantic_ai.models.Model)

        with patch("areyouok_telegram.llms.models.OpenAIModel") as mock_openai:
            mock_openai.return_value = mock_primary

            result = config.model
            assert result == mock_primary

    @patch("areyouok_telegram.llms.models.OPENAI_API_KEY", None)
    @patch("areyouok_telegram.llms.models.OPENROUTER_API_KEY", "test-openrouter-key")
    def test_model_property_returns_openrouter_model_only(self):
        """Test model property returns openrouter model when only openrouter model is available."""
        # This tests lines 48-49: elif self.openrouter_model: return self.openrouter_model
        config = BaseModelConfig(
            model_id="gpt-4",
            provider="openai",
            openrouter_id="openai/gpt-4-turbo",
        )

        mock_openrouter = MagicMock(spec=pydantic_ai.models.Model)

        with (
            patch("areyouok_telegram.llms.models.OpenAIModel") as mock_openai,
            patch("areyouok_telegram.llms.models.OpenRouterProvider") as mock_provider,
        ):
            mock_openai.return_value = mock_openrouter
            mock_provider.return_value = MagicMock(spec=OpenRouterProvider)

            result = config.model
            assert result == mock_openrouter

    @patch("areyouok_telegram.llms.models.OPENAI_API_KEY", None)
    @patch("areyouok_telegram.llms.models.OPENROUTER_API_KEY", None)
    def test_model_property_raises_configuration_error_when_no_models(self):
        """Test model property raises ModelConfigurationError when no models are available."""
        # This tests lines 50-51: else: raise ModelConfigurationError()
        config = BaseModelConfig(
            model_id="gpt-4",
            provider="openai",
        )

        with pytest.raises(ModelConfigurationError) as exc_info:
            _ = config.model

        assert "No valid model configuration found" in str(exc_info.value)
