from areyouok_telegram.data import Chats
from areyouok_telegram.data import Context
from areyouok_telegram.data import ContextType
from areyouok_telegram.data import Messages
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.agent_content_check import ContentCheckDependencies
from areyouok_telegram.llms.agent_content_check import ContentCheckResponse
from areyouok_telegram.llms.agent_content_check import content_check_agent
from areyouok_telegram.llms.chat.responses import DoNothingResponse
from areyouok_telegram.llms.chat.responses import ReactionResponse
from areyouok_telegram.llms.chat.responses import SwitchPersonalityResponse
from areyouok_telegram.llms.chat.responses import TextResponse
from areyouok_telegram.llms.exceptions import InvalidMessageError
from areyouok_telegram.llms.exceptions import ReactToSelfError
from areyouok_telegram.llms.exceptions import ResponseRestrictedError
from areyouok_telegram.llms.exceptions import UnacknowledgedImportantMessageError
from areyouok_telegram.llms.utils import run_agent_with_tracking

AgentResponse = TextResponse | ReactionResponse | SwitchPersonalityResponse | DoNothingResponse


def check_restricted_responses(*, response: AgentResponse, restricted: set[str]) -> None:
    if "text" in restricted and response.response_type == "TextResponse":
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
    if response.response_type != "TextResponse":
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


async def log_metadata_update_context(
    *,
    chat_id: str,
    session_id: str,
    content: str,
) -> None:
    """Log a metadata update to the context table.

    Args:
        chat_id: The chat ID where the update occurred
        session_id: The session ID where the update occurred
        field: The metadata field that was updated
        new_value: The new value that was set
    """
    async with async_database() as db_conn:
        chat_obj = await Chats.get_by_id(db_conn, chat_id=chat_id)
        chat_encryption_key = chat_obj.retrieve_key()

        await Context.new_or_update(
            db_conn,
            chat_encryption_key=chat_encryption_key,
            chat_id=chat_id,
            session_id=session_id,
            ctype=ContextType.METADATA.value,
            content=content,
        )
