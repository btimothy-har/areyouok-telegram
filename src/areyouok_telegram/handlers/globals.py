from datetime import UTC
from datetime import datetime
from datetime import timedelta

import logfire
import telegram
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from areyouok_telegram.data import Chats
from areyouok_telegram.data import Users
from areyouok_telegram.data import async_database
from areyouok_telegram.jobs import ConversationJob
from areyouok_telegram.jobs import schedule_job
from areyouok_telegram.utils import db_retry


async def on_new_update(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    @db_retry()
    async def _handle_update():
        async with async_database() as db_conn:
            if update.effective_user:
                await Users.new_or_update(db_conn, user=update.effective_user)

            if update.effective_chat:
                await Chats.new_or_update(db_conn, chat=update.effective_chat)

    # Don't use `traced` decorator here to avoid circular logging issues
    with logfire.span(
        "New update received.",
        _span_name="handlers.globals.on_new_update",
        update=update,
    ):
        await _handle_update()

    # Only schedule the job if the update is from a private chat
    # This prevents unnecessary job scheduling for group chats or channel, which we don't support yet.
    if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
        await schedule_job(
            context=context,
            job=ConversationJob(chat_id=str(update.effective_chat.id)),
            interval=timedelta(milliseconds=500),
            first=datetime.now(UTC) + timedelta(seconds=2),
        )
