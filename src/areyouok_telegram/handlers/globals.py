import traceback
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import logfire
import telegram
from telegram.constants import ChatType
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from areyouok_telegram.config import DEVELOPER_CHAT_ID
from areyouok_telegram.config import DEVELOPER_THREAD_ID
from areyouok_telegram.data import Chats
from areyouok_telegram.data import Updates
from areyouok_telegram.data import Users
from areyouok_telegram.data import async_database
from areyouok_telegram.jobs import ConversationJob
from areyouok_telegram.jobs import schedule_job
from areyouok_telegram.utils import db_retry


@db_retry()
async def on_new_update(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    # Don't use `traced` decorator here to avoid circular logging issues
    with logfire.span(
        "New update received.",
        _span_name="handlers.globals.on_new_update",
        update=update,
    ):
        async with async_database() as db_conn:
            if update.effective_user:
                user_obj = await Users.new_or_update(db_conn=db_conn, user=update.effective_user)
                # Decrypt user's encryption key
                user_obj.retrieve_key()

            if update.effective_chat:
                await Chats.new_or_update(db_conn=db_conn, chat=update.effective_chat)

    # Only schedule the job if the update is from a private chat
    # This prevents unnecessary job scheduling for group chats or channel, which we don't support yet.
    if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
        await schedule_job(
            context=context,
            job=ConversationJob(chat_id=str(update.effective_chat.id)),
            interval=timedelta(seconds=10),
            first=datetime.now(UTC) + timedelta(seconds=10),
        )


async def on_error_event(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""

    logfire.exception(str(context.error), _exc_info=context.error)

    if update:
        async with async_database() as db_conn:
            await Updates.new_or_upsert(db_conn, update=update)

    if DEVELOPER_CHAT_ID:
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)

        # Escape backticks in the traceback for MarkdownV2 code block
        tb_string = tb_string.replace("`", "\\`")

        message = f"An exception was raised while handling an update\n\n```\n{tb_string}\n```"

        await context.bot.send_message(
            chat_id=DEVELOPER_CHAT_ID,
            message_thread_id=DEVELOPER_THREAD_ID,
            text=message,
            disable_notification=True,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        logfire.info("Error notification sent to developer.")
