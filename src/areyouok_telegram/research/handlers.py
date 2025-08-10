import asyncio
from datetime import UTC
from datetime import datetime

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.config import CHAT_SESSION_TIMEOUT_MINS
from areyouok_telegram.data import Messages
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import Users
from areyouok_telegram.data import async_database
from areyouok_telegram.handlers.exceptions import NoMessageError
from areyouok_telegram.handlers.media_utils import extract_media_from_telegram_message
from areyouok_telegram.research.model import ResearchScenario

from .constants import END_NO_ACTIVE_SESSION
from .constants import FEEDBACK_REQUEST
from .constants import NO_FEEDBACK_REQUEST
from .constants import RESEARCH_ACTIVE_SESSION_INFO
from .constants import RESEARCH_START_INFO
from .utils import generate_feedback_url


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
            if len(messages) < 0:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=NO_FEEDBACK_REQUEST,
                )
            else:
                scenario = await ResearchScenario.get_for_session_id(
                    db_conn=db_conn,
                    session_id=active_session.session_id,
                )

                feedback_url = await generate_feedback_url(
                    session_id=active_session.session_id,
                    metadata=scenario.scenario_config if scenario else "No scenario",
                )
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=FEEDBACK_REQUEST.format(feedback_url=feedback_url),
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
        # Get user and their encryption key
        user_obj = await Users.get_by_id(db_conn, str(update.effective_user.id))
        user_encryption_key = user_obj.retrieve_key(update.effective_user.username)

        extract_media = asyncio.create_task(
            extract_media_from_telegram_message(db_conn, user_encryption_key, message=update.message)
        )

        # Handle session management
        chat_id = str(update.effective_chat.id)
        active_session = await Sessions.get_active_session(db_conn, chat_id)

        # Save the message
        await Messages.new_or_update(
            db_conn,
            user_encryption_key,
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            message=update.message,
            session_key=active_session.session_key if active_session else None,
        )

        if active_session:
            # Record new user message if there is an active session - distinct from the main handler
            await active_session.new_message(db_conn=db_conn, timestamp=update.message.date, is_user=True)

        await extract_media
