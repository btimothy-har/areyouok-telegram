from dataclasses import dataclass

import pydantic
import pydantic_ai

from areyouok_telegram.llms.models import GPT5Nano


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


content_check_agent = pydantic_ai.Agent(
    model=GPT5Nano().model,
    output_type=ContentCheckResponse,
    name="content_check_agent",
    end_strategy="exhaustive",
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
