import asyncio
import random

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data.models import Chat, Message, Session, User
from areyouok_telegram.handlers.commands.feedback import generate_feedback_context
from areyouok_telegram.handlers.exceptions import (
    NoChatFoundError,
    NoEditedMessageError,
    NoMessageError,
    NoMessageReactionError,
    NoUserFoundError,
)
from areyouok_telegram.handlers.utils.media import extract_media_from_telegram_message
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import telegram_call


@traced(extract_args=["update"])
async def on_new_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        raise NoMessageError(update.update_id)

    chat = await Chat.get_by_id(telegram_chat_id=update.effective_chat.id)
    if not chat:
        raise NoChatFoundError(update.effective_chat.id)

    user = await User.get_by_id(telegram_user_id=update.effective_user.id)
    if not user:
        raise NoUserFoundError(update.effective_user.id)

    session = await Session.get_or_create_new_session(
        chat=chat,
        session_start=update.message.date,
    )

    await telegram_call(
        context.bot.send_chat_action,
        chat_id=update.effective_chat.id,
        action=telegram.constants.ChatAction.TYPING,
    )

    # Save message
    message = Message.from_telegram(
        user_id=user.id,
        chat=chat,
        message=update.message,
        session_id=session.id,
    )
    await message.save()

    # Update session
    await session.new_message(
        timestamp=update.message.date,
        is_user=True,
    )

    # Extract media if present
    await extract_media_from_telegram_message(
        chat,
        message=update.message,
        session_id=session.id,
    )

    # Pre-generate / cache context at random
    if random.random() < 1 / 3:
        asyncio.create_task(
            generate_feedback_context(
                bot_id=str(context.bot.id),
                session=session,
            )
        )


@traced(extract_args=["update"])
async def on_edit_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.edited_message:
        raise NoEditedMessageError(update.update_id)

    chat = await Chat.get_by_id(telegram_chat_id=update.effective_chat.id)
    if not chat:
        raise NoChatFoundError(update.effective_chat.id)

    user = await User.get_by_id(telegram_user_id=update.effective_user.id)
    if not user:
        raise NoUserFoundError(update.effective_user.id)

    session = await Session.get_or_create_new_session(
        chat=chat,
        session_start=update.edited_message.date,
    )

    # Save edited message
    message = Message.from_telegram(
        user_id=user.id,
        chat=chat,
        message=update.edited_message,
        session_id=session.id,
    )
    await message.save()

    # Update session activity (not message count)
    await session.new_activity(
        timestamp=update.edited_message.edit_date or update.edited_message.date,
        is_user=True,
    )


@traced(extract_args=["update"])
async def on_message_react(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    """Handle reactions to messages."""
    if not update.message_reaction:
        raise NoMessageReactionError(update.update_id)

    chat = await Chat.get_by_id(telegram_chat_id=update.effective_chat.id)
    if not chat:
        raise NoChatFoundError(update.effective_chat.id)

    user = await User.get_by_id(telegram_user_id=update.effective_user.id)
    if not user:
        raise NoUserFoundError(update.effective_user.id)

    session = await Session.get_or_create_new_session(
        chat=chat,
        session_start=update.message_reaction.date,
    )

    # Save reaction
    message = Message.from_telegram(
        user_id=user.id,
        chat=chat,
        message=update.message_reaction,
        session_id=session.id,
    )
    await message.save()

    # Update session activity (not message count)
    await session.new_activity(
        timestamp=update.message_reaction.date,
        is_user=True,
    )
