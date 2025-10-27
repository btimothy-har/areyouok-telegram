"""Handler for /journal command to initiate journaling sessions."""

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data.models import Chat, CommandUsage, GuidedSession, Message, Session, User
from areyouok_telegram.data.models.messaging import GuidedSessionState, GuidedSessionType, JournalContextMetadata
from areyouok_telegram.handlers.exceptions import NoChatFoundError, NoUserFoundError
from areyouok_telegram.handlers.utils.constants import MD2_JOURNAL_START_MESSAGE
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import telegram_call


@traced(extract_args=["update"])
async def on_journal_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /journal command to start a new journaling session."""

    chat = await Chat.get_by_id(telegram_chat_id=update.effective_chat.id)
    if not chat:
        raise NoChatFoundError(update.effective_chat.id)

    active_session = await Session.get_or_create_new_session(
        chat=chat,
        session_start=update.message.date,
    )

    # Track command usage
    command_usage = CommandUsage(
        chat=chat,
        command="journal",
        session_id=active_session.id,
        timestamp=update.message.date,
    )
    await command_usage.save()

    # Check for existing active guided sessions
    existing_sessions = await GuidedSession.get_by_chat(
        chat=chat,
        session=active_session,
        state=GuidedSessionState.ACTIVE.value,
    )

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

    new_session = GuidedSession(
        chat=chat,
        session=active_session,
        session_type=GuidedSessionType.JOURNALING.value,
        state=GuidedSessionState.ACTIVE.value,
        metadata=initial_metadata.model_dump(),
    )
    new_session = await new_session.save()

    # Record this event in the session
    user = await User.get_by_id(telegram_user_id=update.effective_user.id)
    if not user:
        raise NoUserFoundError(update.effective_user.id)

    message = Message.from_telegram(
        user_id=user.id,
        chat=chat,
        message=update.message,
        session_id=active_session.id,
    )
    message = await message.save()

    await active_session.new_message(
        timestamp=update.message.date,
        is_user=True,
    )

    # Send holding message to user
    await telegram_call(
        context.bot.send_message,
        chat_id=update.effective_chat.id,
        text=MD2_JOURNAL_START_MESSAGE,
        parse_mode="MarkdownV2",
    )
