from datetime import UTC
from datetime import datetime

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import traced

from .constants import END_NO_ACTIVE_SESSION
from .constants import FEEDBACK_REQUEST
from .constants import NO_FEEDBACK_REQUEST
from .constants import RESEARCH_ACTIVE_SESSION_INFO
from .constants import RESEARCH_START_INFO


@traced(extract_args=["update"])
@db_retry()
async def on_start_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if ENV == "research":
        async with async_database() as db_conn:
            active_session = await Sessions.get_active_session(
                db_conn=db_conn,
                chat_id=str(update.effective_chat.id),
            )

            if not active_session:
                await Sessions.create_session(db_conn, str(update.effective_chat.id), update.message.date)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=RESEARCH_START_INFO,
                )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=RESEARCH_ACTIVE_SESSION_INFO,
                )


@traced(extract_args=["update"])
@db_retry()
async def on_end_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if ENV == "research":
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
