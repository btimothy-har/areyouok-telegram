from dataclasses import dataclass

import pydantic_ai

from areyouok_telegram.llms.agent_anonymizer import anonymization_agent
from areyouok_telegram.llms.exceptions import ResponseLengthError
from areyouok_telegram.llms.models import Gemini25Flash
from areyouok_telegram.llms.utils import run_agent_with_tracking


@dataclass
class ContextAgentDependencies:
    tg_chat_id: str
    tg_session_id: str


agent_model = Gemini25Flash(
    model_settings=pydantic_ai.models.google.GoogleModelSettings(
        temperature=0.0,
        google_thinking_config={"thinking_budget": 0},
    ),
)

feedback_context_agent = pydantic_ai.Agent(
    model=agent_model.model,
    name="feedback_context_agent",
    end_strategy="exhaustive",
)


@feedback_context_agent.instructions
def generate_instructions() -> str:
    return """
The agent's only purpose is conversation contextualization for the purposes of analysis and product improvement.

When presented with a conversation history between a user and an assistant, the agent will write a contextualized \
summary of the conversation, being as factual and objective as possible. The contextualized summary should be \
written for a 3rd party reviewer to understand the context of the conversation and understand the user's experience \
with the assistant.

The contextualized summary should be anonymous, taking care to exclude any personally identifiable information \
about the user or assistant.

Output the contextualized summary as a single paragraph, with no line breaks or special characters. Your output must \
be in English, in less than 1,000 characters.
    """


@feedback_context_agent.output_validator
async def validate_output(ctx: pydantic_ai.RunContext, data: str) -> str:
    if len(data) > 1000:
        raise ResponseLengthError(length=len(data), max_length=1000)

    anon_text = await run_agent_with_tracking(
        anonymization_agent,
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        run_kwargs={
            "user_prompt": data,
        },
    )
    return anon_text.output
