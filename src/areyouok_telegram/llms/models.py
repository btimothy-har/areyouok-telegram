from typing import Literal

import pydantic_ai
from google.genai.types import HarmBlockThreshold
from google.genai.types import HarmCategory
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from areyouok_telegram.config import ANTHROPIC_API_KEY
from areyouok_telegram.config import GEMINI_API_KEY
from areyouok_telegram.config import OPENAI_API_KEY
from areyouok_telegram.config import OPENROUTER_API_KEY
from areyouok_telegram.llms.exceptions import ModelConfigurationError
from areyouok_telegram.llms.utils import should_retry_llm_error


class BaseModelConfig:
    """Base class for model configuration."""

    def __init__(
        self,
        model_id: str,
        provider: Literal["openai", "anthropic", "google", "openrouter"],
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
            return OpenAIChatModel(
                model_name=self.model_id,
                settings=self.model_settings,
            )
        elif self.provider == "google" and GEMINI_API_KEY:
            return GoogleModel(
                model_name=self.model_id,
                provider=GoogleProvider(api_key=GEMINI_API_KEY),
                settings=self.model_settings,
            )
        return None

    @property
    def openrouter_model(self) -> pydantic_ai.models.Model | None:
        """Return the OpenRouter model for this configuration."""
        if self.openrouter_id and OPENROUTER_API_KEY:
            return OpenAIChatModel(
                model_name=self.openrouter_id,
                provider=OpenRouterProvider(api_key=OPENROUTER_API_KEY),
                settings=self.model_settings,
            )
        return None


class ClaudeOpus41(BaseModelConfig):
    """Model configuration for Claude Opus 4.1."""

    DEFAULT_SETTINGS = pydantic_ai.settings.ModelSettings(
        temperature=0.0,
    )

    def __init__(self, model_settings: pydantic_ai.settings.ModelSettings | None = None):
        super().__init__(
            model_id="claude-opus-4-1-20250805",
            provider="anthropic",
            openrouter_id="anthropic/claude-opus-4.1",
            model_settings=pydantic_ai.settings.merge_model_settings(self.DEFAULT_SETTINGS, model_settings),
        )


class ClaudeSonnet4(BaseModelConfig):
    """Model configuration for Claude Sonnet 4."""

    DEFAULT_SETTINGS = pydantic_ai.settings.ModelSettings(
        temperature=0.0,
    )

    def __init__(self, model_settings: pydantic_ai.settings.ModelSettings | None = None):
        super().__init__(
            model_id="claude-sonnet-4-20250514",
            provider="anthropic",
            openrouter_id="anthropic/claude-sonnet-4",
            model_settings=pydantic_ai.settings.merge_model_settings(self.DEFAULT_SETTINGS, model_settings),
        )


class GPT5(BaseModelConfig):
    """Model configuration for GPT-5."""

    DEFAULT_SETTINGS = pydantic_ai.settings.ModelSettings(
        temperature=0.0,
    )

    def __init__(self, model_settings: pydantic_ai.settings.ModelSettings | None = None):
        super().__init__(
            model_id="gpt-5-2025-08-07",
            provider="openai",
            openrouter_id="openai/gpt-5",
            model_settings=pydantic_ai.settings.merge_model_settings(self.DEFAULT_SETTINGS, model_settings),
        )


class GPT5Mini(BaseModelConfig):
    """Model configuration for GPT-5 Mini."""

    DEFAULT_SETTINGS = pydantic_ai.settings.ModelSettings(
        temperature=0.0,
    )

    def __init__(self, model_settings: pydantic_ai.settings.ModelSettings | None = None):
        super().__init__(
            model_id="gpt-5-mini-2025-08-07",
            provider="openai",
            openrouter_id="openai/gpt-5-mini",
            model_settings=pydantic_ai.settings.merge_model_settings(self.DEFAULT_SETTINGS, model_settings),
        )


class GPT5Nano(BaseModelConfig):
    """Model configuration for GPT-5 Nano."""

    DEFAULT_SETTINGS = pydantic_ai.settings.ModelSettings(
        temperature=0.0,
    )

    def __init__(self, model_settings: pydantic_ai.settings.ModelSettings | None = None):
        super().__init__(
            model_id="gpt-5-nano-2025-08-07",
            provider="openai",
            openrouter_id="openai/gpt-5-nano",
            model_settings=pydantic_ai.settings.merge_model_settings(self.DEFAULT_SETTINGS, model_settings),
        )


class Gemini25Pro(BaseModelConfig):
    """Model configuration for Google Gemini 2.5 Pro."""

    DEFAULT_SETTINGS = GoogleModelSettings(
        temperature=0.0,
        google_thinking_config={"thinking_budget": -1},
        google_safety_settings=[
            {
                "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
                "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
                "threshold": HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
            },
        ],
    )

    def __init__(self, model_settings: pydantic_ai.settings.ModelSettings | None = None):
        super().__init__(
            model_id="gemini-2.5-pro",
            provider="google",
            openrouter_id="google/gemini-2.5-pro",
            model_settings=pydantic_ai.settings.merge_model_settings(self.DEFAULT_SETTINGS, model_settings),
        )


class Gemini25Flash(BaseModelConfig):
    """Model configuration for Google Gemini 2.5 Flash."""

    DEFAULT_SETTINGS = GoogleModelSettings(
        temperature=0.0,
        google_thinking_config={"thinking_budget": -1},
        google_safety_settings=[
            {
                "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
                "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
                "threshold": HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
            },
        ],
    )

    def __init__(self, model_settings: pydantic_ai.settings.ModelSettings | None = None):
        super().__init__(
            model_id="gemini-2.5-flash",
            provider="google",
            openrouter_id="google/gemini-2.5-flash",
            model_settings=pydantic_ai.settings.merge_model_settings(self.DEFAULT_SETTINGS, model_settings),
        )


class MultiModelConfig:
    """Configuration for multiple models with fallback."""

    def __init__(self, models: list[BaseModelConfig]):
        self.models = models

    @property
    def model(self) -> pydantic_ai.models.Model:
        available_models = []

        for m in self.models:
            if m.primary_model is not None:
                available_models.append(m.primary_model)
            if m.openrouter_model is not None:
                available_models.append(m.openrouter_model)

        if not available_models:
            raise ModelConfigurationError()

        if len(available_models) == 1:
            return available_models[0]

        return FallbackModel(
            *available_models,
            fallback_on=should_retry_llm_error,
        )
