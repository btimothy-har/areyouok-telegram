"""Context search agent for analyzing past conversation history."""

import pydantic
import pydantic_ai

from areyouok_telegram.llms.models import GPT5


class ContextSearchResponse(pydantic.BaseModel):
    """Response from context search agent with answer and summary."""

    answer: str = pydantic.Field(
        description="Direct answer to the search query using the retrieved conversation contexts."
    )
    summary: str = pydantic.Field(
        description="Concise summary of the retrieved contexts, highlighting key themes and patterns."
    )


agent_model = GPT5(
    model_settings=pydantic_ai.settings.ModelSettings(
        temperature=0.2,
    ),
)

context_search_agent = pydantic_ai.Agent(
    model=agent_model.model,
    output_type=ContextSearchResponse,
    name="context_search_agent",
    end_strategy="exhaustive",
    retries=3,
)


@context_search_agent.instructions
def generate_instructions() -> str:
    return """
You are a context search assistant that helps analyze past user interactions.

You will be provided with:
1. A search query describing what information to find
2. Retrieved conversation contexts from the user's past interactions

Your task is to:
1. Answer the search query directly using information from the retrieved contexts
2. Provide a concise summary of the retrieved contexts, highlighting key themes, patterns, and relevant details

Guidelines:
- Be specific and factual, directly referencing information from the contexts
- If the contexts don't contain relevant information to answer the query, say so clearly
- In your summary, organize information thematically rather than chronologically
- Keep both answer and summary concise but informative
- Maintain the emotional tone and context from the original conversations
    """


@context_search_agent.output_validator
async def validate_output(ctx: pydantic_ai.RunContext, data: ContextSearchResponse) -> ContextSearchResponse:  # noqa: ARG001
    """Validate the output from the context search agent."""
    return data
