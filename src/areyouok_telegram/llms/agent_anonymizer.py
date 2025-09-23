import pydantic_ai

from areyouok_telegram.llms.models import GPT5Nano

agent_model = GPT5Nano(
    model_settings=pydantic_ai.models.openai.OpenAIChatModelSettings(openai_reasoning_effort="minimal")
)

anonymization_agent = pydantic_ai.Agent(
    model=agent_model.model,
    name="anonymization_agent",
    end_strategy="exhaustive",
    retries=3,
)


@anonymization_agent.instructions
def generate_instructions() -> str:
    return """
You are a text anonymization assistant. Your task is to anonymize the given text by removing \
sensitive information while retaining the essence and meaning of the original message.

Replace names, locations, specific identifiers, and other potentially identifying information with \
generic placeholders. Maintain the emotional tone and context of the message.
    """


@anonymization_agent.output_validator
async def validate_anonymous_output(ctx: pydantic_ai.RunContext, data: str) -> str:  # noqa: ARG001
    return data
