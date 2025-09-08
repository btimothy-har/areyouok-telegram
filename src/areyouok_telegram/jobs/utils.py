from datetime import UTC
from datetime import datetime
from typing import Any

import pydantic_ai
import telegram

from areyouok_telegram.data import Context
from areyouok_telegram.data import ContextType
from areyouok_telegram.data import GuidedSessions
from areyouok_telegram.data import GuidedSessionType
from areyouok_telegram.data import Messages
from areyouok_telegram.data import MessageTypes
from areyouok_telegram.data import Notifications
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.chat import chat_agent
from areyouok_telegram.utils import db_retry


@db_retry()
async def get_all_inactive_sessions(from_dt: datetime, to_dt: datetime) -> list["Sessions"]:
    """
    Retrieve all inactive sessions that ended within the specified time range.
    """
    async with async_database() as db_conn:
        return await Sessions.get_all_inactive_sessions(db_conn, from_dt, to_dt)


@db_retry()
async def get_next_notification(chat_id: str) -> Notifications | None:
    """
    Get the next pending notification for a chat.

    Args:
        chat_id: The chat ID to get the next notification for

    Returns:
        The next pending notification, or None if no pending notifications exist
    """
    async with async_database() as db_conn:
        return await Notifications.get_next_pending(db_conn, chat_id=chat_id)


@db_retry()
async def mark_notification_completed(notification: Notifications) -> None:
    """
    Mark a notification as completed.

    Args:
        notification: The notification to mark as completed
    """
    async with async_database() as db_conn:
        await notification.mark_as_completed(db_conn)


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
            user_encryption_key=chat_encryption_key,
            user_id=bot_id,  # Bot's user ID as the sender
            chat_id=chat_id,
            message=message,
            session_key=chat_session.session_id,  # Use the session key for the chat session
            reasoning=reasoning,  # Store AI reasoning
        )

        if isinstance(message, telegram.Message):
            await chat_session.new_message(
                db_conn,
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
            db_conn,
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
            chat_encryption_key=chat_encryption_key,
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
    close_ts = datetime.now(UTC)

    async with async_database() as db_conn:
        # Check for any active guided sessions (onboarding, etc.) linked to this session
        onboarding_sessions = await GuidedSessions.get_by_chat_session(
            db_conn, chat_session=chat_session.session_key, session_type=GuidedSessionType.ONBOARDING.value
        )

        # Inactivate any active onboarding sessions
        for onboarding in onboarding_sessions:
            if onboarding.is_active:
                await onboarding.inactivate(db_conn, timestamp=close_ts)

        await chat_session.close_session(
            db_conn,
            timestamp=close_ts,
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
