import asyncio
import logging
import traceback

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from areyouok_telegram.config import DEVELOPER_CHAT_ID
from areyouok_telegram.data import Chats
from areyouok_telegram.data import Updates
from areyouok_telegram.data import Users
from areyouok_telegram.data import async_database_session

logger = logging.getLogger(__name__)


async def on_new_update(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa:ARG001
    async with async_database_session() as session:
        await Updates.new_or_upsert(session, update=update)

        update_tasks = []
        if update.effective_user:
            update_tasks.append(asyncio.create_task(Users.new_or_update(session=session, user=update.effective_user)))

        if update.effective_chat:
            update_tasks.append(asyncio.create_task(Chats.new_or_update(session=session, chat=update.effective_chat)))

        await asyncio.gather(*update_tasks)


async def on_error_event(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error(f"Exception while handling an update: {update.update_id}", exc_info=context.error)

    if DEVELOPER_CHAT_ID:
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)

        message = f"An exception was raised while handling an update\n\n{tb_string}"

        await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN_V2)
