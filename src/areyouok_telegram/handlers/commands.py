import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import Chats
from areyouok_telegram.data import Messages
from areyouok_telegram.data import GuidedSessions
from areyouok_telegram.data import GuidedSessionType
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.handlers.constants import ONBOARDING_COMPLETE_MESSAGE
from areyouok_telegram.research.handlers import on_end_command_research
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import environment_override
from areyouok_telegram.utils import traced


@traced(extract_args=["update"])
@db_retry()
async def on_start_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    async with async_database() as db_conn:
        # Get chat and its encryption key
        chat_obj = await Chats.get_by_id(db_conn, chat_id=str(update.effective_chat.id))
        chat_encryption_key = chat_obj.retrieve_key()

        # Handle session management
        chat_id = str(update.effective_chat.id)
        active_session = await Sessions.get_active_session(db_conn, chat_id=chat_id)

        if not active_session:
            active_session = await Sessions.create_session(db_conn, chat_id=chat_id, timestamp=update.message.date)

        # Check for existing onboarding sessions for this chat
        onboarding_sessions = await GuidedSessions.get_by_chat_id(
            db_conn,
            chat_id=str(update.effective_chat.id),
            session_type=GuidedSessionType.ONBOARDING.value,
        )
        
        # Get the most recent onboarding session (first in desc order)
        onboarding_session = onboarding_sessions[0] if onboarding_sessions else None

        if onboarding_session and onboarding_session.is_completed:
            return await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=ONBOARDING_COMPLETE_MESSAGE,
            )

        elif not onboarding_session or onboarding_session.is_incomplete:
            await GuidedSessions.start_new_session(
                db_conn,
                user_id=str(update.effective_user.id),
                chat_session=active_session.session_key,
                session_type=GuidedSessionType.ONBOARDING.value,
            )

        await Messages.new_or_update(
            db_conn,
            user_encryption_key=chat_encryption_key,
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            message=update.message,
            session_key=active_session.session_key,
        )
        await active_session.new_activity(db_conn, timestamp=update.message.date, is_user=True)


@traced(extract_args=["update"])
@environment_override(
    {
        "research": on_end_command_research,
    }
)
@db_retry()
async def on_end_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    return
