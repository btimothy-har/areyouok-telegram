from datetime import UTC
from datetime import datetime
from typing import Any

import pydantic_ai
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import Chats
from areyouok_telegram.data import Context
from areyouok_telegram.data import ContextType
from areyouok_telegram.data import Messages
from areyouok_telegram.data import MessageTypes
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.jobs.exceptions import UserNotFoundForChatError
from areyouok_telegram.llms.chat import chat_agent
from areyouok_telegram.research.agents import close_research_session
from areyouok_telegram.research.agents import generate_agent_for_research_session
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import environment_override


@db_retry()
async def get_chat_session(chat_id: str) -> "Sessions":
    """
    Retrieve the active session for a given chat ID.
    """
    async with async_database() as db_conn:
        return await Sessions.get_active_session(db_conn, chat_id)


@db_retry()
async def get_chat_encryption_key(chat_id: str) -> str:
    """
    Get the chat encryption key for a given chat_id.

    Args:
        chat_id: The chat ID to get the encryption key for

    Returns:
        The chat's encryption key

    Raises:
        UserNotFoundForChatError: If no chat is found (will be renamed to ChatNotFoundError later)
    """
    async with async_database() as db_conn:
        chat_obj = await Chats.get_by_id(db_conn, chat_id)

        if not chat_obj:
            raise UserNotFoundForChatError(chat_id)

        return chat_obj.retrieve_key()


@db_retry()
async def get_all_inactive_sessions(from_dt: datetime, to_dt: datetime) -> list["Sessions"]:
    """
    Retrieve all inactive sessions that ended within the specified time range.
    """
    async with async_database() as db_conn:
        return await Sessions.get_all_inactive_sessions(db_conn, from_dt, to_dt)


@db_retry()
async def log_bot_message(
    *,
    bot_id: str,
    chat_encryption_key: str,
    chat_id: str,
    chat_session: Sessions,
    message: MessageTypes,
    reasoning: str,
) -> None:
    async with async_database() as db_conn:
        await Messages.new_or_update(
            db_conn,
            chat_encryption_key,
            user_id=bot_id,  # Bot's user ID as the sender
            chat_id=chat_id,
            message=message,
            session_key=chat_session.session_id,  # Use the session key for the chat session
            reasoning=reasoning,  # Store AI reasoning
        )

        if isinstance(message, telegram.Message):
            await chat_session.new_message(
                db_conn=db_conn,
                timestamp=message.date,
                is_user=False,  # This is a bot response
            )


@db_retry()
async def log_bot_activity(
    *,
    chat_session: Sessions,
    timestamp: datetime,
) -> None:
    async with async_database() as db_conn:
        # Always create a new activity for the bot, even if no response message is provided
        await chat_session.new_activity(
            db_conn=db_conn,
            timestamp=timestamp,
            is_user=False,  # This is a bot response
        )


@db_retry()
async def save_session_context(
    *,
    chat_encryption_key: str,
    chat_id: str,
    chat_session: Sessions,
    ctype: ContextType,
    data: Any,
):
    """
    Create a session context for the given chat ID.
    If no session exists, create a new one.
    """
    async with async_database() as db_conn:
        await Context.new_or_update(
            db_conn,
            chat_encryption_key,
            chat_id=chat_id,
            session_id=chat_session.session_id,
            ctype=ctype.value,
            content=data,
        )


@db_retry()
async def close_chat_session(chat_session: Sessions):
    """
    Close the chat session and clean up any resources.
    """
    async with async_database() as db_conn:
        await chat_session.close_session(
            db_conn=db_conn,
            timestamp=datetime.now(UTC),
        )


@environment_override(
    {
        "research": generate_agent_for_research_session,
    }
)
async def generate_chat_agent(chat_session: Sessions) -> pydantic_ai.Agent:  # noqa: ARG001
    """
    Generate the chat agent for a conversation job.
    Primarily used to allow for ENV-specific injection of different chat agents.

    Args:
        context: The context for the chat agent.
        chat_session: The chat session for which the agent is being generated.

    Returns:
        pydantic_ai.Agent: The generated chat agent.
    """
    return chat_agent


@environment_override(
    {
        "research": close_research_session,
    }
)
async def post_cleanup_tasks(
    *,
    context: ContextTypes.DEFAULT_TYPE,  # noqa: ARG001
    chat_session: Sessions,  # noqa: ARG001
) -> None:
    """
    Perform any post-cleanup tasks after closing a chat session.
    This can include logging, notifications, or other cleanup actions.

    Primarily used to allow for ENV-specific injection of different post-cleanup tasks.
    """
    return
