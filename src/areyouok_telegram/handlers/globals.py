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
from areyouok_telegram.utils import split_long_message
from areyouok_telegram.utils import telegram_call


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
            interval=timedelta(seconds=3),
            first=datetime.now(UTC) + timedelta(seconds=2),
        )


async def on_error_event(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""

    @db_retry()
    async def _save_update():
        async with async_database() as db_conn:
            await Updates.new_or_upsert(db_conn, update=update)

    logfire.exception(str(context.error), _exc_info=context.error)

    if update:
        await _save_update()

    if isinstance(context.error, (telegram.error.NetworkError, telegram.error.TimedOut)):
        return

    if DEVELOPER_CHAT_ID:
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)

        # Escape backticks in the traceback for MarkdownV2 code block
        tb_string = tb_string.replace("`", "\\`")
        full_message = f"An exception was raised while handling an update\n\n```\n{tb_string}\n```"

        # Split the message if it's too long
        message_chunks = split_long_message(full_message)

        for i, message_chunk in enumerate(message_chunks):
            final_message = message_chunk
            if len(message_chunks) > 1:
                # Add part indicator for multi-part messages
                chunk_header = f"*Part {i + 1}/{len(message_chunks)}*\n\n"
                final_message = chunk_header + message_chunk

            try:
                await telegram_call(
                    context.bot.send_message,
                    chat_id=DEVELOPER_CHAT_ID,
                    message_thread_id=DEVELOPER_THREAD_ID,
                    text=final_message,
                    disable_notification=True,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            except Exception as e:
                logfire.exception(
                    "Failed to send error notification to developer",
                    _exc_info=e,
                    chat_id=DEVELOPER_CHAT_ID,
                    thread_id=DEVELOPER_THREAD_ID,
                )

                try:
                    await telegram_call(
                        context.bot.send_message,
                        chat_id=DEVELOPER_CHAT_ID,
                        message_thread_id=DEVELOPER_THREAD_ID,
                        text="Error: Failed to send error notification to developer. Please check logs.",
                        disable_notification=True,
                    )
                except Exception as fallback_error:
                    logfire.exception(
                        "Fallback error notification to developer failed.",
                        _exc_info=fallback_error,
                        chat_id=DEVELOPER_CHAT_ID,
                        thread_id=DEVELOPER_THREAD_ID,
                    )

        logfire.info(f"Error notification sent to developer ({len(message_chunks)} parts).")
