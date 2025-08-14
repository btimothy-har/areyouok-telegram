from typing import Literal

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
    """Reply with a text message to the user, optionally replying to a specific message."""

    message_text: str = pydantic.Field(description="The text message to send as a reply to the user.")
    reply_to_message_id: str | None = pydantic.Field(
        default=None, description="Message ID to reply to, if replying directly to a message. Use only when necessary."
    )


class ReactionResponse(BaseAgentResponse):
    """React to a message (user's or agent's) with an emoji."""

    react_to_message_id: str = pydantic.Field(description="The message ID to react to with an emoji.")
    emoji: ReactionEmoji = pydantic.Field(description="The emoji to use for the reaction.")


class SwitchPersonalityResponse(BaseAgentResponse):
    """Switch to a different personality for this conversation."""

    personality: Literal["anchoring", "celebration", "exploration", "witnessing"] = pydantic.Field(
        description="The name of the personality to switch to."
    )


class DoNothingResponse(BaseAgentResponse):
    """Do nothing response, used when no action is needed."""


AgentResponse = TextResponse | ReactionResponse | SwitchPersonalityResponse | DoNothingResponse
