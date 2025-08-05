import asyncio

import logfire
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import Messages
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database_session
from areyouok_telegram.handlers.exceptions import NoEditedMessageError
from areyouok_telegram.handlers.exceptions import NoMessageError
from areyouok_telegram.handlers.exceptions import NoMessageReactionError

from .utils import extract_media_from_telegram_message


async def on_new_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.message:
        raise NoMessageError(update.update_id)

    with logfire.span(
        "New message received.",
        _span_name="handlers.messages.on_new_message",
        message_id=update.message.message_id,
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
    ):
        async with async_database_session() as session:
            # Save the message
            with logfire.span(
                "Saving new message to database.",
                _span_name="handlers.messages.on_new_message.save_message",
            ):
                await Messages.new_or_update(
                    session, user_id=update.effective_user.id, chat_id=update.effective_chat.id, message=update.message
                )

            extract_media = asyncio.create_task(extract_media_from_telegram_message(session, update.message))

            with logfire.span(
                "Logging session activity.",
                _span_name="handlers.messages.on_new_message.log_session_activity",
            ):
                # Handle session management
                chat_id = str(update.effective_chat.id)
                active_session = await Sessions.get_active_session(session, chat_id)

                if active_session:
                    # Record new user message
                    await active_session.new_message(update.message.date, is_user=True)
                    logfire.info("Session activity recorded.")
                else:
                    # Create new session and record the first message
                    new_session = await Sessions.create_session(session, chat_id, update.message.date)
                    await new_session.new_message(update.message.date, is_user=True)
                    logfire.info("New session started.")

            await extract_media


async def on_edit_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.edited_message:
        raise NoEditedMessageError(update.update_id)

    with logfire.span(
        "Edited message received.",
        _span_name="handlers.messages.on_edit_message",
        message_id=update.edited_message.message_id,
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
    ):
        async with async_database_session() as session:
            # Save the edited message
            with logfire.span(
                "Saving edited message to database.",
                _span_name="handlers.messages.on_edit_message.save_message",
            ):
                await Messages.new_or_update(
                    session,
                    user_id=update.effective_user.id,
                    chat_id=update.effective_chat.id,
                    message=update.edited_message,
                )

            # Handle session management for edits
            active_session = await Sessions.get_active_session(session, str(update.effective_chat.id))

            if not active_session:
                logfire.info("No active session found for edited message, skipping session activity.")
                return

            # Only extract media if there's an active session
            extract_media = asyncio.create_task(extract_media_from_telegram_message(session, update.edited_message))

            with logfire.span(
                "Logging session activity.",
                _span_name="handlers.messages.on_edit_message.log_session_activity",
            ):
                # Only record user activity if the original message was sent after session start
                if update.edited_message.date >= active_session.session_start:
                    await active_session.new_activity(
                        update.edited_message.edit_date or update.edited_message.date, is_user=True
                    )
                    logfire.info("Session activity recorded for edited message.")
                else:
                    logfire.info(
                        "Edited message is from before session start, not recording activity.",
                        message_id=update.edited_message.message_id,
                        session_start=active_session.session_start,
                    )

            await extract_media


async def on_message_react(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    """Handle reactions to messages."""
    if not update.message_reaction:
        raise NoMessageReactionError(update.update_id)

    with logfire.span(
        "Message reaction received.",
        _span_name="handlers.messages.on_message_react",
        message_id=update.message_reaction.message_id,
        chat_id=update.effective_chat.id,
    ):
        async with async_database_session() as session:
            # Save the reaction
            with logfire.span(
                "Saving message reaction to database.",
                _span_name="handlers.messages.on_message_react.save_reaction",
            ):
                await Messages.new_or_update(
                    session,
                    user_id=update.effective_user.id,
                    chat_id=update.effective_chat.id,
                    message=update.message_reaction,
                )

            with logfire.span(
                "Logging session activity.",
                _span_name="handlers.messages.on_message_react.log_session_activity",
            ):
                # Handle session management for reactions
                active_session = await Sessions.get_active_session(session, str(update.effective_chat.id))

                if not active_session:
                    logfire.info("No active session found for message reaction, skipping session activity.")
                    return

                # Only record user activity if the original message was sent after session start
                if update.message_reaction.date >= active_session.session_start:
                    await active_session.new_activity(update.message_reaction.date, is_user=True)
                    logfire.info("Session activity recorded for message reaction.")
                else:
                    logfire.info(
                        "Message reaction is from before session start, not recording activity.",
                        message_id=update.message_reaction.message_id,
                        session_start=active_session.session_start,
                    )
