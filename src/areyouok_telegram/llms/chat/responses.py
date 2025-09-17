from typing import Literal

import pydantic
from telegram.constants import ReactionEmoji


class _KeyboardButton(pydantic.BaseModel):
    """A button for the keyboard response."""

    text: str = pydantic.Field(
        description=(
            "The text to display on the button. When the user presses the button, "
            "this text will be sent to yoou as a message from the user. "
            "Max of 50 characters."
        ),
        max_length=50,
    )


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


class KeyboardResponse(TextResponse):
    """
    Display a one-time keyboard to the text message, forcing the user to select their response from a fixed list.
    Each keyboard can only have a maximum of 5 buttons.
    Button text should be phrased in the user's perspective, as if they are responding to the agent.
    """

    tooltip_text: str = pydantic.Field(
        description="Tooltip text to display in the chatbox to the user, providing context.",
        min_length=1,
        max_length=64,
    )
    buttons: list[_KeyboardButton] = pydantic.Field(
        description="A list of buttons to display on the keyboard for the user to choose from.",
        min_length=1,
        max_length=5,
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
