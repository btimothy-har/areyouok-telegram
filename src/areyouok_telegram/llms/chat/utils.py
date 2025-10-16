from dataclasses import dataclass, field
from typing import Literal

from areyouok_telegram.data import Messages, Notifications, async_database
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

    tg_bot_id: str
    tg_chat_id: str
    tg_session_id: str
    restricted_responses: set[Literal["text", "reaction", "switch_personality", "keyboard"]] = field(
        default_factory=set
    )
    notification: Notifications | None = None

    def to_dict(self) -> dict:
        return {
            "tg_bot_id": self.tg_bot_id,
            "tg_chat_id": self.tg_chat_id,
            "tg_session_id": self.tg_session_id,
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


async def validate_response_data(*, response: AgentResponse, chat_id: str, bot_id: str) -> None:
    if response.response_type == "ReactionResponse":
        async with async_database() as db_conn:
            message, _ = await Messages.retrieve_message_by_id(
                db_conn=db_conn,
                message_id=response.react_to_message_id,
                chat_id=chat_id,
            )

        if not message:
            raise InvalidMessageError(response.react_to_message_id)

        if message.user_id == str(bot_id):
            raise ReactToSelfError(response.react_to_message_id)


async def check_special_instructions(
    *, response: AgentResponse, chat_id: str, session_id: str, instruction: str
) -> None:
    if response.response_type not in ("TextResponse", "TextWithButtonsResponse", "KeyboardResponse"):
        raise UnacknowledgedImportantMessageError(instruction)

    else:
        content_check_run = await run_agent_with_tracking(
            agent=content_check_agent,
            chat_id=chat_id,
            session_id=session_id,
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
