import logging

from telegram import Update
from telegram.ext import ContextTypes

from areyouok_telegram.data import async_database_session
from areyouok_telegram.data import new_or_upsert_message

from .exceptions import NoMessageError

logger = logging.getLogger(__name__)


async def on_new_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        raise NoMessageError(update.update_id)

    async with async_database_session() as session:
        await new_or_upsert_message(session, user_id=context._user_id, chat_id=context._chat_id, message=update.message)


async def on_edit_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.edited_message:
        raise NoMessageError(update.update_id)

    async with async_database_session() as session:
        await new_or_upsert_message(
            session, user_id=context._user_id, chat_id=context._chat_id, message=update.edited_message
        )
