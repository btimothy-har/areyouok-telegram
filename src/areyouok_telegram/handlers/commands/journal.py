"""Handler for /journal command to initiate journaling sessions."""

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import (
    GuidedSessions,
    GuidedSessionType,
    JournalContextMetadata,
    Sessions,
    operations as data_operations,
)
from areyouok_telegram.data.connection import async_database
from areyouok_telegram.handlers.constants import MD2_JOURNAL_START_MESSAGE
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import db_retry, telegram_call


@traced(extract_args=["update"])
async def on_journal_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /journal command to start a new journaling session."""

    active_session = await data_operations.get_or_create_active_session(
        chat_id=str(update.effective_chat.id),
        timestamp=update.message.date,
    )

    await data_operations.track_command_usage(
        command="journal",
        chat_id=str(update.effective_chat.id),
        session_id=active_session.session_id,
    )

    existing_sessions = await data_operations.get_active_guided_sessions(session=active_session)

    if existing_sessions:
        await telegram_call(
            context.bot.send_message,
            chat_id=update.effective_chat.id,
            text=(
                f"You already have an active {existing_sessions[0].session_type.capitalize()} session. "
                "Please complete it before using this command."
            ),
        )
        return

    initial_metadata = JournalContextMetadata(
        phase="topic_selection",
        generated_topics=[],
        selected_topic=None,
    )

    await initialize_journaling_session(
        chat_id=str(update.effective_chat.id),
        session=active_session,
        chat_encryption_key=await data_operations.get_chat_encryption_key(chat_id=str(update.effective_chat.id)),
        initial_metadata=initial_metadata,
    )

    # Record this event in the session
    await data_operations.new_session_event(
        session=active_session,
        message=update.message,
        user_id=str(update.effective_user.id),
        is_user=True,
    )

    # Send holding message to user
    await telegram_call(
        context.bot.send_message,
        chat_id=update.effective_chat.id,
        text=MD2_JOURNAL_START_MESSAGE,
        parse_mode="MarkdownV2",
    )


@db_retry()
async def initialize_journaling_session(
    *,
    chat_id: str,
    session: Sessions,
    chat_encryption_key: str,
    initial_metadata: JournalContextMetadata,
) -> None:
    """Initialize a new journaling session."""
    async with async_database() as db_conn:
        await GuidedSessions.start_new_session(
            db_conn,
            chat_id=chat_id,
            chat_session=session.session_id,
            session_type=GuidedSessionType.JOURNALING.value,
        )

        all_sessions = await GuidedSessions.get_by_chat_session(
            db_conn,
            chat_session=session.session_id,
            session_type=GuidedSessionType.JOURNALING.value,
        )

        active_session = [s for s in all_sessions if s.is_active][0]

        # Update with encrypted metadata
        await active_session.update_metadata(
            db_conn,
            metadata=initial_metadata.model_dump(),
            chat_encryption_key=chat_encryption_key,
        )
