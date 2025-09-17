from typing import Literal

import pydantic
from telegram.constants import ReactionEmoji


class _KeyboardButton(pydantic.BaseModel):
    """A button for the keyboard response."""

    text: str = pydantic.Field(
        description=(
            "The text to display on the button. Emojis are allowed. When the user presses the button, "
            "this text will be sent to you as a message from the user. "
            "Max of 50 characters."
        ),
        max_length=50,
    )


class _MessageButton(pydantic.BaseModel):
    """A button attached to a message."""

    label: str = pydantic.Field(
        description="The text to display on the button. Emojis are allowed.",
        max_length=50,
    )
    callback: str = pydantic.Field(
        description="The information you want to receive when the user presses the button.",
        max_length=40,
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


class TextWithButtonsResponse(TextResponse):
    """
    Attach a set of buttons to a text message.
    Buttons are permanently attached to the message and can be pressed multiple times.
    Actions taken by the user are injected into context, instead of being sent as a message.
    User will still be able to type freeform messages as normal.
    """

    buttons: list[_MessageButton] = pydantic.Field(
        description="A list of buttons to attach to the message.",
        min_length=1,
        max_length=3,
    )
    buttons_per_row: int = pydantic.Field(
        description="Number of buttons to display per row. Must be between 1 and 5, recommended default is 3.",
        ge=1,
        le=5,
    )
    context: str = pydantic.Field(
        description=(
            "Context documentation for the assistant to understand the purpose of the buttons. "
            "Include a description of each of the callbacks used in the buttons, and what they correspond to."
        ),
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
