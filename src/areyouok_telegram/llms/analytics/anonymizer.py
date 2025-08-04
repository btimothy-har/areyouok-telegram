import pydantic_ai
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from areyouok_telegram.config import OPENROUTER_API_KEY
from areyouok_telegram.llms.utils import pydantic_ai_instrumentation

agent_models = FallbackModel(
    OpenAIModel(model_name="gpt-4.1-nano-2025-04-14"),
    OpenAIModel(
        model_name="openai/gpt-4.1-nano",
        provider=OpenRouterProvider(api_key=OPENROUTER_API_KEY),
    ),
)


anonymization_agent = pydantic_ai.Agent(
    model=agent_models,
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
