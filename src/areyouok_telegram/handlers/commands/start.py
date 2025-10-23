import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data.models import Chat, CommandUsage, GuidedSession, Message, Session, User
from areyouok_telegram.data.models.messaging import GuidedSessionState, GuidedSessionType
from areyouok_telegram.handlers.exceptions import NoChatFoundError, NoUserFoundError
from areyouok_telegram.handlers.utils.constants import MD2_ONBOARDING_COMPLETE_MESSAGE, MD2_ONBOARDING_START_MESSAGE
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import telegram_call


@traced(extract_args=["update"])
async def on_start_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
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
        command="start",
        session_id=active_session.id,
        timestamp=update.message.date,
    )
    await command_usage.save()

    # Check for existing onboarding sessions
    guided_sessions = await GuidedSession.get_by_chat(
        chat=chat,
        session_type=GuidedSessionType.ONBOARDING.value,
    )
    onboarding_session = guided_sessions[0] if guided_sessions else None

    if onboarding_session and onboarding_session.is_completed:
        await telegram_call(
            context.bot.send_message,
            chat_id=update.effective_chat.id,
            text=MD2_ONBOARDING_COMPLETE_MESSAGE,
            parse_mode="MarkdownV2",
        )
        return

    elif not onboarding_session or onboarding_session.is_incomplete:
        new_session = GuidedSession(
            chat=chat,
            session=active_session,
            session_type=GuidedSessionType.ONBOARDING.value,
            state=GuidedSessionState.ACTIVE.value,
        )
        await new_session.save()

    user = await User.get_by_id(telegram_user_id=update.effective_user.id)
    if not user:
        raise NoUserFoundError(update.effective_user.id)

    message = Message.from_telegram(
        user_id=user.id,
        chat=chat,
        message=update.message,
        session_id=active_session.id,
    )
    await message.save()

    await active_session.new_message(
        timestamp=update.message.date,
        is_user=True,
    )

    if not active_session.last_bot_activity:
        await telegram_call(
            context.bot.send_message,
            chat_id=update.effective_chat.id,
            text=MD2_ONBOARDING_START_MESSAGE,
            parse_mode="MarkdownV2",
        )
