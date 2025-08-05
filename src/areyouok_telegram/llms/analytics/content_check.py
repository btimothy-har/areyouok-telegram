from dataclasses import dataclass

import pydantic
import pydantic_ai
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIModel

from areyouok_telegram.llms.utils import openrouter_provider
from areyouok_telegram.llms.utils import pydantic_ai_instrumentation


@dataclass
class ContentCheckDependencies:
    """Context data passed to the LLM agent."""

    check_content_exists: str


class ContentCheckResponse(pydantic.BaseModel):
    """Model for context template used in session compression."""

    check_pass: bool = pydantic.Field(
        description="Indicates whether the content check passed.",
    )
    feedback: str = pydantic.Field(
        description="Your feedback on the content check, including any suggestions for improvement.",
    )


model_settings = pydantic_ai.settings.ModelSettings(temperature=0.0)

agent_models = FallbackModel(
    OpenAIModel(
        model_name="gpt-4.1-mini-2025-04-14",
        settings=model_settings,
    ),
    OpenAIModel(
        model_name="openai/gpt-4.1-mini",
        provider=openrouter_provider,
        settings=model_settings,
    ),
)


content_check_agent = pydantic_ai.Agent(
    model=agent_models,
    output_type=ContentCheckResponse,
    name="content_check_agent",
    end_strategy="exhaustive",
    instrument=pydantic_ai_instrumentation,
)


@content_check_agent.instructions
def content_check_instructions(ctx: pydantic_ai.RunContext[ContentCheckDependencies]) -> str:
    return f"""
Validate that the provided message adheres to the following instruction:

"{ctx.deps.check_content_exists}"

The message need not be explicitly adherent, as long as it implies a similar meaning or intent.

If the message does not adhere to the instruction, provide feedback on how it can be improved.
If the message adheres to the instruction, return "No Feedback Needed" as feedback.
    """
