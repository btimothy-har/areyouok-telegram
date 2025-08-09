import pydantic_ai

from areyouok_telegram.llms.models import VALIDATOR_GPT_5_NANO
from areyouok_telegram.llms.utils import pydantic_ai_instrumentation

anonymization_agent = pydantic_ai.Agent(
    model=VALIDATOR_GPT_5_NANO.model,
    name="anonymization_agent",
    end_strategy="exhaustive",
    instrument=pydantic_ai_instrumentation,
)


@anonymization_agent.instructions
def generate_instructions() -> str:
    return """
You are a text anonymization assistant. Your task is to anonymize sensitive information \
in the provided text while retaining the essence and meaning of the original message.

Replace names, locations, specific identifiers, and other potentially identifying information with \
generic placeholders. Maintain the emotional tone and context of the message.
    """


@anonymization_agent.output_validator
async def validate_anonymous_output(ctx: pydantic_ai.RunContext, data: str) -> str:  # noqa: ARG001
    return data
