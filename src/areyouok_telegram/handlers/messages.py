import logging

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import Messages
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database_session
from areyouok_telegram.handlers.exceptions import NoEditedMessageError
from areyouok_telegram.handlers.exceptions import NoMessageError

logger = logging.getLogger(__name__)


async def on_new_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.message:
        raise NoMessageError(update.update_id)

    async with async_database_session() as session:
        # Save the message
        await Messages.new_or_update(
            session, user_id=update.effective_user.id, chat_id=update.effective_chat.id, message=update.message
        )

        # Handle session management
        chat_id = str(update.effective_chat.id)
        active_session = await Sessions.get_active_session(session, chat_id)

        if active_session:
            # Record new user message
            await active_session.new_message(update.message.date, "user")
        else:
            # Create new session and record the first message
            new_session = await Sessions.create_session(session, chat_id, update.message.date)
            await new_session.new_message(update.message.date, "user")


async def on_edit_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.edited_message:
        raise NoEditedMessageError(update.update_id)

    async with async_database_session() as session:
        # Save the edited message
        await Messages.new_or_update(
            session, user_id=update.effective_user.id, chat_id=update.effective_chat.id, message=update.edited_message
        )

        # Handle session management for edits
        chat_id = str(update.effective_chat.id)
        active_session = await Sessions.get_active_session(session, chat_id)

        if active_session:
            # Only record user activity if the original message was sent after session start
            if update.edited_message.date >= active_session.session_start:
                await active_session.new_user_activity(update.edited_message.edit_date or update.edited_message.date)
            # If message is from before session start, don't record activity
        # If no active session, don't create one for edits
