from datetime import UTC
from datetime import datetime

import logfire
import pydantic_ai
import telegram

from areyouok_telegram.data.connection import async_database
from areyouok_telegram.data.models.chat_event import SYSTEM_USER_ID
from areyouok_telegram.data.models.chats import Chats
from areyouok_telegram.data.models.command_usage import CommandUsage
from areyouok_telegram.data.models.context import Context
from areyouok_telegram.data.models.guided_sessions import GuidedSessions
from areyouok_telegram.data.models.guided_sessions import GuidedSessionType
from areyouok_telegram.data.models.llm_generations import LLMGenerations
from areyouok_telegram.data.models.llm_usage import LLMUsage
from areyouok_telegram.data.models.messages import Messages
from areyouok_telegram.data.models.sessions import Sessions
from areyouok_telegram.utils.media import extract_media_from_telegram_message
from areyouok_telegram.utils.media import handle_unsupported_media
from areyouok_telegram.utils.retry import db_retry


class InvalidChatError(Exception):
    """Raised when no chat is found for a given chat_id.

    This typically occurs when trying to access a chat that doesn't exist
    in the database or hasn't been initialized yet.
    """

    def __init__(self, chat_id: str):
        """Initialize the exception with the chat_id that caused the error."""
        super().__init__(f"No chat found for chat_id {chat_id}.")
        self.chat_id = chat_id


class MissingGuidedSessionTypeError(RuntimeError):
    def __init__(self):
        message = "Guided Session Type must be provided."
        super().__init__(message)


@db_retry()
async def get_or_create_active_session(
    *,
    chat_id: str,
    timestamp: datetime | None = None,
    create_if_not_exists: bool = True,
) -> Sessions | None:
    timestamp = timestamp or datetime.now(UTC)

    async with async_database() as db_conn:
        active_session = await Sessions.get_active_session(db_conn, chat_id=chat_id)

        if create_if_not_exists and not active_session:
            active_session = await Sessions.create_session(db_conn, chat_id=chat_id, timestamp=timestamp)

        # Eagerly load critical attributes to prevent DetachedInstanceError
        # when the session object is used outside this database context
        if active_session:
            _ = active_session.chat_id
            _ = active_session.session_id
            _ = active_session.session_start

    return active_session if active_session else None


@db_retry()
async def get_or_create_guided_session(
    *,
    chat_id: str,
    session: Sessions,
    stype: GuidedSessionType | None = None,
    create_if_not_exists: bool = True,
) -> GuidedSessions | None:
    async with async_database() as db_conn:
        all_sessions_of_type = await GuidedSessions.get_by_chat_id(
            db_conn,
            chat_id=chat_id,
            session_type=stype.value if stype else None,
        )

        if create_if_not_exists and not all_sessions_of_type:
            if not stype:
                raise MissingGuidedSessionTypeError()

            await GuidedSessions.start_new_session(
                db_conn,
                chat_id=chat_id,
                chat_session=session.session_id,
                session_type=stype.value,
            )

            all_sessions_of_type = await GuidedSessions.get_by_chat_session(
                db_conn,
                chat_session=session.session_id,
                session_type=stype.value,
            )

    return all_sessions_of_type[0] if all_sessions_of_type else None


@db_retry()
async def new_session_event(
    *,
    session: Sessions,
    message: telegram.Message | telegram.MessageReactionUpdated,
    user_id: str,
    is_user: bool,
    reasoning: str | None = None,
):
    async with async_database() as db_conn:
        chat_obj = await Chats.get_by_id(db_conn, chat_id=session.chat_id)

        await Messages.new_or_update(
            db_conn,
            user_encryption_key=chat_obj.retrieve_key(),
            user_id=user_id,
            chat_id=session.chat_id,
            message=message,
            session_key=session.session_id,
            reasoning=reasoning,
        )

        # Intentionally do not log a new session message/activity for system messages.
        # Only LLM-generated messages should count to bot session activities.
        if user_id != SYSTEM_USER_ID:
            if isinstance(message, telegram.Message) and message.date >= session.session_start:
                await session.new_message(db_conn, timestamp=message.date, is_user=is_user)
                if message.edit_date:
                    await session.new_activity(db_conn, timestamp=message.edit_date, is_user=is_user)

            if isinstance(message, telegram.MessageReactionUpdated) and message.date >= session.session_start:
                await session.new_activity(db_conn, timestamp=message.date, is_user=is_user)

        if isinstance(message, telegram.Message):
            media_count = await extract_media_from_telegram_message(
                db_conn,
                chat_obj.retrieve_key(),
                message=message,
                session_id=session.session_id,
            )

            if media_count > 0 and is_user:
                await handle_unsupported_media(
                    db_conn,
                    chat_id=session.chat_id,
                    message_id=str(message.message_id),
                )


@db_retry()
async def close_chat_session(*, chat_session: Sessions):
    """
    Close the chat session and clean up any resources.
    """
    close_ts = datetime.now(UTC)

    async with async_database() as db_conn:
        # Check for any active guided sessions (onboarding, etc.) linked to this session
        # Inactivate any active onboarding sessions

        guided_sessions = await GuidedSessions.get_by_chat_session(
            db_conn,
            chat_session=chat_session.session_id,
        )

        if guided_sessions:
            for s in guided_sessions:
                if s.is_active:
                    await s.inactivate(db_conn, timestamp=close_ts)

        await chat_session.close_session(
            db_conn,
            timestamp=close_ts,
        )


@db_retry()
async def get_chat_encryption_key(*, chat_id: str) -> str:
    """Get the encryption key for a chat.

    Args:
        chat_id: Chat identifier

    Returns:
        str: The decrypted Fernet encryption key

    Raises:
        InvalidChatError: If no chat is found
    """
    async with async_database() as db_conn:
        chat_obj = await Chats.get_by_id(db_conn, chat_id=chat_id)

        if not chat_obj:
            raise InvalidChatError(chat_id)

        return chat_obj.retrieve_key()


@db_retry()
async def get_latest_profile(*, chat_id: str) -> Context | None:
    """Get the latest profile context for a chat, with content decrypted and cached.

    Args:
        chat_id: Chat identifier

    Returns:
        Context | None: Profile context with decrypted content cached, or None if no profile exists

    Raises:
        InvalidChatError: If no chat is found
    """
    async with async_database() as db_conn:
        profile_context = await Context.get_latest_profile(db_conn, chat_id=chat_id)
        if profile_context:
            encryption_key = await get_chat_encryption_key(chat_id=chat_id)
            profile_context.decrypt_content(chat_encryption_key=encryption_key)
            return profile_context

    return None


@db_retry()
async def track_command_usage(
    *,
    command: str,
    chat_id: str,
    session_id: str | None = None,
):
    """Track command usage for analytics and monitoring.

    Args:
        command: Command name (e.g., "start", "preferences")
        chat_id: Chat identifier
        session_id: Session identifier
    """
    async with async_database() as db_conn:
        await CommandUsage.track_command(
            db_conn,
            command=command,
            chat_id=chat_id,
            session_id=session_id,
        )


@db_retry()
async def track_llm_usage(
    *,
    chat_id: str,
    session_id: str,
    agent: pydantic_ai.Agent,
    result: pydantic_ai.agent.AgentRunResult,
    runtime: float,
    run_kwargs: dict,
) -> None:
    try:
        async with async_database() as db_conn:
            # Track usage data
            await LLMUsage.track_pydantic_usage(
                db_conn=db_conn,
                chat_id=chat_id,
                session_id=session_id,
                agent=agent,
                data=result.usage(),
                runtime=runtime,
            )
            await LLMGenerations.create(
                db_conn=db_conn,
                chat_id=chat_id,
                session_id=session_id,
                agent=agent,
                run_result=result,
                run_deps=run_kwargs.get("deps"),
            )

    except Exception as e:
        # Log the error but don't raise it
        logfire.exception(
            f"Failed to log LLM usage: {e}",
            agent=agent.name,
            chat_id=chat_id,
            session_id=session_id,
        )
