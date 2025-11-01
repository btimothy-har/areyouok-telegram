from dataclasses import dataclass, field
from typing import Literal

from areyouok_telegram.data.models import Chat, Message, Notification, Session, User
from areyouok_telegram.llms.agent_content_check import (
    ContentCheckDependencies,
    ContentCheckResponse,
    content_check_agent,
)
from areyouok_telegram.llms.chat.responses import (
    DoNothingResponse,
    ReactionResponse,
    SwitchPersonalityResponse,
    TextResponse,
    TextWithButtonsResponse,
)
from areyouok_telegram.llms.exceptions import (
    InvalidMessageError,
    ReactToSelfError,
    ResponseRestrictedError,
    UnacknowledgedImportantMessageError,
)
from areyouok_telegram.llms.utils import run_agent_with_tracking

AgentResponse = (
    TextResponse | TextWithButtonsResponse | ReactionResponse | SwitchPersonalityResponse | DoNothingResponse
)


@dataclass
class CommonChatAgentDependencies:
    """Common dependencies for chat agents."""

    bot_id: int  # Telegram bot user ID
    user: User
    chat: Chat
    session: Session
    restricted_responses: set[Literal["text", "reaction", "switch_personality", "keyboard"]] = field(
        default_factory=set
    )
    notification: Notification | None = None

    def to_dict(self) -> dict:
        return {
            "bot_id": self.bot_id,
            "user_id": self.user.id,
            "chat_id": self.chat.id,
            "session_id": self.session.id,
            "restricted_responses": list(self.restricted_responses),
            "notification_content": self.notification.content if self.notification else None,
        }


def check_restricted_responses(*, response: AgentResponse, restricted: set[str]) -> None:
    if "text" in restricted and response.response_type in (
        "TextResponse",
        "TextWithButtonsResponse",
        "KeyboardResponse",
    ):
        raise ResponseRestrictedError(response.response_type)

    if "keyboard" in restricted and response.response_type == "KeyboardResponse":
        raise ResponseRestrictedError(response.response_type)

    if "reaction" in restricted and response.response_type == "ReactionResponse":
        raise ResponseRestrictedError(response.response_type)

    if "switch_personality" in restricted and response.response_type == "SwitchPersonalityResponse":
        raise ResponseRestrictedError(response.response_type)


async def validate_response_data(*, response: AgentResponse, chat: Chat, bot_id: int) -> None:
    if response.response_type == "ReactionResponse":
        message = await Message.get_by_id(
            chat=chat,
            telegram_message_id=int(response.react_to_message_id),
        )

        if not message:
            raise InvalidMessageError(response.react_to_message_id)

        # Get bot's internal user ID for comparison
        bot_user = await User.get_by_id(telegram_user_id=bot_id)
        if bot_user and message.user_id == bot_user.id:
            raise ReactToSelfError(response.react_to_message_id)


async def check_special_instructions(
    *, response: AgentResponse, chat: Chat, session: Session, instruction: str
) -> None:
    if response.response_type not in ("TextResponse", "TextWithButtonsResponse", "KeyboardResponse"):
        raise UnacknowledgedImportantMessageError(instruction)

    else:
        content_check_run = await run_agent_with_tracking(
            agent=content_check_agent,
            chat=chat,
            session=session,
            run_kwargs={
                "user_prompt": response.message_text,
                "deps": ContentCheckDependencies(
                    check_content_exists=instruction,
                ),
            },
        )

        content_check: ContentCheckResponse = content_check_run.output

        if not content_check.check_pass:
            raise UnacknowledgedImportantMessageError(instruction, content_check.feedback)
