from typing import Literal

import pydantic_ai
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from areyouok_telegram.config import ANTHROPIC_API_KEY
from areyouok_telegram.config import OPENAI_API_KEY
from areyouok_telegram.config import OPENROUTER_API_KEY
from areyouok_telegram.llms.exceptions import ModelConfigurationError
from areyouok_telegram.llms.utils import should_retry_llm_error


class BaseModelConfig:
    """Base class for model configuration."""

    def __init__(
        self,
        model_id: str,
        provider: Literal["openai", "anthropic"] = "openai",
        openrouter_id: str | None = None,
        model_settings: pydantic_ai.settings.ModelSettings | None = None,
    ):
        self.model_id = model_id
        self.provider = provider

        self.openrouter_id = openrouter_id
        self.model_settings = model_settings

    @property
    def model(self) -> pydantic_ai.models.Model:
        if self.primary_model and self.openrouter_model:
            return FallbackModel(
                self.primary_model,
                self.openrouter_model,
                fallback_on=should_retry_llm_error,
            )
        elif self.primary_model:
            return self.primary_model
        elif self.openrouter_model:
            return self.openrouter_model
        else:
            raise ModelConfigurationError()

    @property
    def primary_model(self) -> pydantic_ai.models.Model | None:
        """Return the primary model for this configuration."""
        if self.provider == "anthropic" and ANTHROPIC_API_KEY:
            return AnthropicModel(
                model_name=self.model_id,
                settings=self.model_settings,
            )
        elif self.provider == "openai" and OPENAI_API_KEY:
            return OpenAIModel(
                model_name=self.model_id,
                settings=self.model_settings,
            )
        return None

    @property
    def openrouter_model(self) -> pydantic_ai.models.Model | None:
        """Return the OpenRouter model for this configuration."""
        if self.openrouter_id and OPENROUTER_API_KEY:
            return OpenAIModel(
                model_name=self.openrouter_id,
                provider=OpenRouterProvider(api_key=OPENROUTER_API_KEY),
                settings=self.model_settings,
            )
        return None


class ClaudeSonnet4(BaseModelConfig):
    """Model configuration for Claude Sonnet 4."""

    DEFAULT_SETTINGS = pydantic_ai.settings.ModelSettings(
        temperature=0.6,
        parallel_tool_calls=False,
    )

    def __init__(self, model_settings: pydantic_ai.settings.ModelSettings | None = None):
        super().__init__(
            model_id="claude-sonnet-4-20250514",
            provider="anthropic",
            openrouter_id="anthropic/claude-sonnet-4",
            model_settings=model_settings or self.DEFAULT_SETTINGS,
        )


class GPT5Nano(BaseModelConfig):
    """Model configuration for GPT-5 Nano."""

    DEFAULT_SETTINGS = pydantic_ai.settings.ModelSettings(
        temperature=0.0,
        parallel_tool_calls=False,
    )

    def __init__(self, model_settings: pydantic_ai.settings.ModelSettings | None = None):
        super().__init__(
            model_id="gpt-5-nano-2025-08-07",
            provider="openai",
            openrouter_id="openai/gpt-5-nano",
            model_settings=model_settings or self.DEFAULT_SETTINGS,
        )
