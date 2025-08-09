import asyncio
from datetime import UTC
from datetime import datetime

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.config import CHAT_SESSION_TIMEOUT_MINS
from areyouok_telegram.data import Messages
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.handlers.exceptions import NoMessageError
from areyouok_telegram.handlers.media_utils import extract_media_from_telegram_message
from areyouok_telegram.research.model import ResearchScenario

from .constants import END_NO_ACTIVE_SESSION
from .constants import FEEDBACK_REQUEST
from .constants import NO_FEEDBACK_REQUEST
from .constants import RESEARCH_ACTIVE_SESSION_INFO
from .constants import RESEARCH_START_INFO


async def on_start_command_research(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    async with async_database() as db_conn:
        active_session = await Sessions.get_active_session(
            db_conn=db_conn,
            chat_id=str(update.effective_chat.id),
        )

        if not active_session:
            session = await Sessions.create_session(db_conn, str(update.effective_chat.id), update.message.date)
            await ResearchScenario.generate_for_session(
                db_conn=db_conn,
                session_id=session.session_key,
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=RESEARCH_START_INFO.format(chat_session_timeout_mins=CHAT_SESSION_TIMEOUT_MINS),
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=RESEARCH_ACTIVE_SESSION_INFO,
            )


async def on_end_command_research(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    async with async_database() as db_conn:
        active_session = await Sessions.get_active_session(
            db_conn=db_conn,
            chat_id=str(update.effective_chat.id),
        )

        if active_session:
            await active_session.close_session(db_conn, datetime.now(UTC))

            messages = await active_session.get_messages(db_conn)
            if len(messages) < 5:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=NO_FEEDBACK_REQUEST,
                )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=FEEDBACK_REQUEST.format(feedback_url="https://yahoo.com"),
                    link_preview_options=telegram.LinkPreviewOptions(is_disabled=False, show_above_text=False),
                )

        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=END_NO_ACTIVE_SESSION,
            )


async def on_new_message_research(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.message:
        raise NoMessageError(update.update_id)

    async with async_database() as db_conn:
        # Save the message
        await Messages.new_or_update(
            db_conn=db_conn, user_id=update.effective_user.id, chat_id=update.effective_chat.id, message=update.message
        )

        extract_media = asyncio.create_task(extract_media_from_telegram_message(db_conn, update.message))

        # Handle session management
        chat_id = str(update.effective_chat.id)
        active_session = await Sessions.get_active_session(db_conn, chat_id)

        if active_session:
            # Record new user message if there is an active session - distinct from the main handler
            await active_session.new_message(db_conn=db_conn, timestamp=update.message.date, is_user=True)

        await extract_media
