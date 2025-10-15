"""Agent for generating contextual journaling prompts based on user history."""

from datetime import UTC, datetime

import pydantic
import pydantic_ai
from pydantic_ai import ModelRetry

from areyouok_telegram.data import Context
from areyouok_telegram.data.models.chat_event import CONTEXT_TYPE_MAP
from areyouok_telegram.llms.models import Gemini25Pro
from areyouok_telegram.utils.text import format_relative_time

FORMATTED_CONTEXT_TEMPLATE = """
<item>
<timestamp>{timestamp}</timestamp>
<type>{type}</type>
<content>{content}</content>
</item>
"""


def construct_journal_context_text(*, journal_context_items: list[Context]) -> str:
    """Construct the text for the journal context."""
    now = datetime.now(UTC)
    return "\n\n".join([
        FORMATTED_CONTEXT_TEMPLATE.format(
            timestamp=format_relative_time(ctx.created_at, reference_time=now),
            type=CONTEXT_TYPE_MAP[ctx.type],
            content=str(ctx.content) if ctx.content else "",
        )
        for ctx in journal_context_items
    ])


class JournalPrompts(pydantic.BaseModel):
    """Model for journal prompt generation response."""

    prompts: list[str] = pydantic.Field(
        description="List of 3 contextual journaling prompts.", min_length=3, max_length=3
    )


agent_model = Gemini25Pro()

journal_prompts_agent = pydantic_ai.Agent(
    model=agent_model.model,
    output_type=JournalPrompts,
    name="journal_prompts_agent",
    end_strategy="exhaustive",
    retries=3,
)


@journal_prompts_agent.instructions
def generate_instructions(ctx: pydantic_ai.RunContext) -> str:  # noqa: ARG001
    return """
Facilitate a journaling session for the user by suggesting 3 themes or prompts to initiate the session.

To guide your task, consider the user's recent interactions with an AI companion, with attention to their \
recent emotional state, topics, or experiences. Use the following categories as a guide:
- Gratitude and appreciation
- Emotional processing and feelings
- Challenges and growth
- Relationships and connections
- Self-reflection and awareness
- Goals and aspirations
- Daily experiences and moments

## Guidelines
- Prompts should be written in the user's perspective.
- Each prompt should be a single sentence, no more than 50 characters.
- Make them specific enough to guide, but open enough to allow freedom.
- Do not include the AI companion in your prompts.
- Contextualize the prompts to the user's recent interactions with the AI companion.

## Examples
- What new skill did I explore today?
- Which moment brought me unexpected joy?
- How did I handle frustration or stress lately?
- What is a quality I admire in someone close to me?
- Where did I notice progress in my goals?
- When did I feel truly present today?
- What am I most grateful for today?
"""


@journal_prompts_agent.output_validator
async def validate_prompts_output(
    ctx: pydantic_ai.RunContext,  # noqa: ARG001
    data: JournalPrompts,
) -> JournalPrompts:
    """Validate that we have exactly 3 unique prompts."""
    if len(data.prompts) != 3:
        raise ModelRetry(f"Expected 3 prompts, got {len(data.prompts)}")  # noqa: TRY003

    if len(set(data.prompts)) != 3:
        raise ModelRetry("Prompts must be unique")  # noqa: TRY003

    for prompt in data.prompts:
        if len(prompt.strip()) == 0:
            raise ModelRetry("Prompts cannot be empty")  # noqa: TRY003
        if len(prompt) >= 50:
            raise ModelRetry(f"Prompt must be less than 50 characters: {prompt!r}")  # noqa: TRY003

    return data
