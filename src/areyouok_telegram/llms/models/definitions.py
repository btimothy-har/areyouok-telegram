import pydantic_ai

from areyouok_telegram.llms.models.base import BaseModelConfig

CHAT_SONNET_3_5 = BaseModelConfig(
    model_name="anthropic/claude-sonnet-3.5",
    provider="anthropic",
    model_id="claude-3-5-sonnet-20241022",
    openrouter_id="anthropic/claude-3.5-sonnet",
    model_settings=pydantic_ai.settings.ModelSettings(
        temperature=0.6,
        parallel_tool_calls=False,
    ),
)

CHAT_SONNET_4 = BaseModelConfig(
    model_name="anthropic/claude-sonnet-4",
    provider="anthropic",
    model_id="claude-sonnet-4-20250514",
    openrouter_id="anthropic/claude-sonnet-4",
    model_settings=pydantic_ai.settings.ModelSettings(
        temperature=0.6,
        parallel_tool_calls=False,
    ),
)

CHAT_GPT_5 = BaseModelConfig(
    model_name="openai/gpt-5",
    provider="openai",
    model_id="gpt-5-2025-08-07",
    openrouter_id="openai/gpt-5",
    model_settings=pydantic_ai.settings.ModelSettings(
        temperature=0.6,
        parallel_tool_calls=False,
    ),
)

VALIDATOR_GPT_5_NANO = BaseModelConfig(
    model_name="openai/gpt-5-nano",
    provider="openai",
    model_id="gpt-5-nano-2025-08-07",
    openrouter_id="openai/gpt-5-nano",
    model_settings=pydantic_ai.settings.ModelSettings(
        temperature=0.0,
    ),
)
