import pydantic
from telegram.constants import ReactionEmoji


class BaseAgentResponse(pydantic.BaseModel):
    """Base class for agent responses."""

    reasoning: str = pydantic.Field(
        description="The reasoning behind the agent's decision, used for debugging and understanding the response."
    )

    @property
    def response_type(self) -> str:
        """Return the type of response as a string."""
        return self.__class__.__name__


class TextResponse(BaseAgentResponse):
    """Response model for text replies."""

    message_text: str = pydantic.Field(description="The text message to send as a reply to the user.")
    reply_to_message_id: str | None = pydantic.Field(
        default=None, description="Message ID to reply to, if replying directly to a message. Use only when necessary."
    )


class ReactionResponse(BaseAgentResponse):
    """Response model for emoji reactions."""

    react_to_message_id: str = pydantic.Field(description="The message ID to react to with an emoji.")
    emoji: ReactionEmoji = pydantic.Field(description="The emoji to use for the reaction.")


class DoNothingResponse(BaseAgentResponse):
    """Response model for do-nothing actions."""


AgentResponse = TextResponse | ReactionResponse | DoNothingResponse
