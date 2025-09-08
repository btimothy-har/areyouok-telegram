import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import SYSTEM_USER_ID
from areyouok_telegram.data import GuidedSessions
from areyouok_telegram.data import GuidedSessionType
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import operations as data_operations
from areyouok_telegram.data.connection import async_database
from areyouok_telegram.handlers.constants import MD2_ONBOARDING_COMPLETE_MESSAGE
from areyouok_telegram.handlers.constants import MD2_ONBOARDING_START_MESSAGE
from areyouok_telegram.logging import traced
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import telegram_call


@traced(extract_args=["update"])
async def on_start_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    active_session = await data_operations.get_or_create_active_session(
        chat_id=str(update.effective_chat.id),
        timestamp=update.message.date,
    )

    onboarding_session = await data_operations.get_or_create_guided_session(
        chat_id=str(update.effective_chat.id), session=active_session, stype=GuidedSessionType.ONBOARDING
    )

    if onboarding_session.is_completed:
        await telegram_call(
            context.bot.send_message,
            chat_id=update.effective_chat.id,
            text=MD2_ONBOARDING_COMPLETE_MESSAGE,
            parse_mode="MarkdownV2",
        )
        return

    elif onboarding_session.is_incomplete:
        await start_new_onboarding_session(session=active_session)

    await data_operations.new_session_event(
        session=active_session,
        message=update.message,
        user_id=str(update.effective_user.id),
        is_user=True,
    )

    if not active_session.last_bot_activity:
        bot_message = await telegram_call(
            context.bot.send_message,
            chat_id=update.effective_chat.id,
            text=MD2_ONBOARDING_START_MESSAGE,
            parse_mode="MarkdownV2",
        )

        await data_operations.new_session_event(
            session=active_session,
            message=bot_message,
            user_id=SYSTEM_USER_ID,
            is_user=False,
        )


@db_retry()
async def start_new_onboarding_session(*, session: Sessions):
    async with async_database() as db_conn:
        await GuidedSessions.start_new_session(
            db_conn,
            chat_id=session.chat_id,
            chat_session=session.session_id,
            session_type=GuidedSessionType.ONBOARDING.value,
        )
