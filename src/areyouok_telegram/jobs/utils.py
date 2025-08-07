from datetime import UTC
from datetime import datetime

import telegram

from areyouok_telegram.data import Context
from areyouok_telegram.data import Messages
from areyouok_telegram.data import MessageTypes
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.analytics import ContextTemplate
from areyouok_telegram.utils import db_retry


@db_retry()
async def get_chat_session(chat_id: str) -> "Sessions":
    """
    Retrieve the active session for a given chat ID.
    """
    async with async_database() as db_conn:
        return await Sessions.get_active_session(db_conn, chat_id)


@db_retry()
async def get_all_inactive_sessions(from_dt: datetime, to_dt: datetime) -> list["Sessions"]:
    """
    Retrieve all inactive sessions that ended within the specified time range.
    """
    async with async_database() as db_conn:
        return await Sessions.get_all_inactive_sessions(db_conn, from_dt, to_dt)


@db_retry()
async def log_bot_activity(
    bot_id: str, chat_id: str, chat_session: Sessions, response_message: MessageTypes | None
) -> None:
    async with async_database() as db_conn:
        if response_message:
            await Messages.new_or_update(
                db_conn=db_conn,
                user_id=bot_id,  # Bot's user ID as the sender
                chat_id=chat_id,
                message=response_message,
            )

            if isinstance(response_message, telegram.Message):
                await chat_session.new_message(
                    db_conn=db_conn,
                    timestamp=response_message.date,
                    is_user=False,  # This is a bot response
                )
        else:
            await chat_session.new_activity(
                db_conn=db_conn,
                timestamp=datetime.now(UTC),
                is_user=False,  # This is a bot response
            )


@db_retry()
async def save_session_context(chat_id: str, chat_session: Sessions, context: ContextTemplate):
    """
    Create a session context for the given chat ID.
    If no session exists, create a new one.
    """
    async with async_database() as db_conn:
        await Context.new_or_update(
            db_conn=db_conn,
            chat_id=chat_id,
            session_id=chat_session.session_id,
            ctype="session",
            content=context.content,
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
