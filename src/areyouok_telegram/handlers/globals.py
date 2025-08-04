import traceback

import logfire
import telegram
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from areyouok_telegram.config import DEVELOPER_CHAT_ID
from areyouok_telegram.data import Chats
from areyouok_telegram.data import Updates
from areyouok_telegram.data import Users
from areyouok_telegram.data import async_database_session
from areyouok_telegram.jobs import schedule_conversation_job


async def on_new_update(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    with logfire.span(
        f"Processing update {update.update_id}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        user_id=update.effective_user.id if update.effective_user else None,
    ):
        async with async_database_session() as session:
            if update.effective_user:
                await Users.new_or_update(session=session, user=update.effective_user)
                logfire.debug("Update User saved.")

            if update.effective_chat:
                await Chats.new_or_update(session=session, chat=update.effective_chat)
                logfire.debug("Update Chat saved.")

                # Schedule conversation job for any update with a chat
                await schedule_conversation_job(context=context, chat_id=str(update.effective_chat.id))

        logfire.debug(
            "Update successfully processed.",
            update_id=update.update_id,
            chat_id=update.effective_chat.id if update.effective_chat else None,
            user_id=update.effective_user.id if update.effective_user else None,
        )


async def on_error_event(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""

    if not update:
        logfire.error(str(context.error), _exc_info=context.error)
    else:
        logfire.error(f"Exception while handling an update: {update.update_id}", _exc_info=context.error)

        # Store update only for debugging
        async with async_database_session() as session:
            await Updates.new_or_upsert(session, update=update)

    if DEVELOPER_CHAT_ID:
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)

        message = f"An exception was raised while handling an update\n\n{tb_string}"

        await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN_V2)
