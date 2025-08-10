import pydantic
import pydantic_ai

from areyouok_telegram.llms.models import CONTEXT_COMPRESSION_CLAUDE_3_5_HAIKU

from .constants import CONNECTION_DESC
from .constants import CONTEXT_TEMPLATE
from .constants import CONVERSATION_DESC
from .constants import FEEDBACK_DESC
from .constants import LIFE_SITUATION_DESC
from .constants import PERSONAL_CONTEXT_DESC
from .constants import PRACTICAL_MATTERS_DESC


class ContextTemplate(pydantic.BaseModel):
    """Model for context template used in session compression."""

    life_situation: str = pydantic.Field(
        description=LIFE_SITUATION_DESC,
    )
    connection: str = pydantic.Field(
        description=CONNECTION_DESC,
    )
    personal_context: str = pydantic.Field(
        description=PERSONAL_CONTEXT_DESC,
    )
    conversation: str = pydantic.Field(
        description=CONVERSATION_DESC,
    )
    practical_matters: str = pydantic.Field(
        description=PRACTICAL_MATTERS_DESC,
    )
    feedback: str = pydantic.Field(
        description=FEEDBACK_DESC,
    )
    others: str = pydantic.Field(
        description="Any other relevant information that does not fit into the above categories.",
    )

    @property
    def content(self) -> str:
        """Return the context template as a formatted string."""
        return CONTEXT_TEMPLATE.format(
            life_situation=self.life_situation,
            connection=self.connection,
            personal_context=self.personal_context,
            conversation=self.conversation,
            practical_matters=self.practical_matters,
            feedback=self.feedback,
            others=self.others,
        )


context_compression_agent = pydantic_ai.Agent(
    model=CONTEXT_COMPRESSION_CLAUDE_3_5_HAIKU.model,
    output_type=ContextTemplate,
    name="context_compression_agent",
    end_strategy="exhaustive",
)


@context_compression_agent.instructions
def context_compression_instructions() -> str:
    return """
You are a context compression assistant for a support chat system.

Your task is to compress the context of the provided chat session, summarizing only the essential elements that \
are necessary for an AI Agent to continue the conversation effectively.

You are provided with 7 fields, each representing a different aspect of the session context. \
Analyze the provided messages and extract the relevant information for each field.

Where there is no relevant information, provide "No relevant information." as your response.
"""
