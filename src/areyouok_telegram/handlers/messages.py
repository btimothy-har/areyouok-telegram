import asyncio
import random

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import operations as data_operations
from areyouok_telegram.handlers.commands.feedback import generate_feedback_context
from areyouok_telegram.handlers.exceptions import NoEditedMessageError, NoMessageError, NoMessageReactionError
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import telegram_call


@traced(extract_args=["update"])
async def on_new_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        raise NoMessageError(update.update_id)

    active_session = await data_operations.get_or_create_active_session(
        chat_id=str(update.effective_chat.id),
        timestamp=update.message.date,
    )

    await telegram_call(
        context.bot.send_chat_action,
        chat_id=update.effective_chat.id,
        action=telegram.constants.ChatAction.TYPING,
    )

    await data_operations.new_session_event(
        session=active_session,
        message=update.message,
        user_id=str(update.effective_user.id),
        is_user=True,
    )

    # Pre-generate / cache context at random
    if random.random() < 1 / 3:
        asyncio.create_task(
            generate_feedback_context(
                bot_id=str(context.bot.id),
                session=active_session,
            )
        )


@traced(extract_args=["update"])
async def on_edit_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.edited_message:
        raise NoEditedMessageError(update.update_id)

    active_session = await data_operations.get_or_create_active_session(
        chat_id=str(update.effective_chat.id),
        timestamp=update.edited_message.date,
    )

    await data_operations.new_session_event(
        session=active_session,
        message=update.edited_message,
        user_id=str(update.effective_user.id),
        is_user=True,
    )


@traced(extract_args=["update"])
async def on_message_react(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    """Handle reactions to messages."""
    if not update.message_reaction:
        raise NoMessageReactionError(update.update_id)

    active_session = await data_operations.get_or_create_active_session(
        chat_id=str(update.effective_chat.id),
        timestamp=update.message_reaction.date,
    )

    await data_operations.new_session_event(
        session=active_session,
        message=update.message_reaction,
        user_id=str(update.effective_user.id),
        is_user=True,
    )
