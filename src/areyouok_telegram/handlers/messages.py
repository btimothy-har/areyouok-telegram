import logging

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import Messages
from areyouok_telegram.data import async_database_session
from areyouok_telegram.handlers.exceptions import NoEditedMessageError
from areyouok_telegram.handlers.exceptions import NoMessageError

logger = logging.getLogger(__name__)


async def on_new_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.message:
        raise NoMessageError(update.update_id)

    async with async_database_session() as session:
        await Messages.new_or_update(
            session, user_id=update.effective_user.id, chat_id=update.effective_chat.id, message=update.message
        )


async def on_edit_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.edited_message:
        raise NoEditedMessageError(update.update_id)

    async with async_database_session() as session:
        await Messages.new_or_update(
            session, user_id=update.effective_user.id, chat_id=update.effective_chat.id, message=update.edited_message
        )
