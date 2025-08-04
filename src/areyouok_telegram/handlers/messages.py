import logfire
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import Messages
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database_session
from areyouok_telegram.handlers.exceptions import NoEditedMessageError
from areyouok_telegram.handlers.exceptions import NoMessageError
from areyouok_telegram.handlers.exceptions import NoMessageReactionError


async def on_new_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.message:
        raise NoMessageError(update.update_id)

    with logfire.span(
        f"Processing new message {update.message.message_id} in chat {update.effective_chat.id}",
        user_id=update.effective_user.id,
    ):
        async with async_database_session() as session:
            # Save the message
            await Messages.new_or_update(
                session, user_id=update.effective_user.id, chat_id=update.effective_chat.id, message=update.message
            )
            logfire.debug("New message saved.")

            # Handle session management
            chat_id = str(update.effective_chat.id)
            active_session = await Sessions.get_active_session(session, chat_id)

            if active_session:
                # Record new user message
                await active_session.new_message(update.message.date, is_user=True)
                logfire.debug("Session activity recorded.")
            else:
                # Create new session and record the first message
                new_session = await Sessions.create_session(session, chat_id, update.message.date)
                await new_session.new_message(update.message.date, is_user=True)
                logfire.debug("New session started.")


async def on_edit_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.edited_message:
        raise NoEditedMessageError(update.update_id)

    with logfire.span(
        f"Processing edited message {update.edited_message.message_id} in chat {update.effective_chat.id}",
        user_id=update.effective_user.id,
    ):
        async with async_database_session() as session:
            # Save the edited message
            await Messages.new_or_update(
                session,
                user_id=update.effective_user.id,
                chat_id=update.effective_chat.id,
                message=update.edited_message,
            )
            logfire.debug("Edited message saved.")

            # Handle session management for edits
            active_session = await Sessions.get_active_session(session, str(update.effective_chat.id))

            if not active_session:
                logfire.debug("No active session found for edited message, skipping session activity.")
                return

            # Only record user activity if the original message was sent after session start
            if update.edited_message.date >= active_session.session_start:
                await active_session.new_activity(
                    update.edited_message.edit_date or update.edited_message.date, is_user=True
                )
                logfire.debug("Session activity recorded for edited message.")
            else:
                logfire.debug(
                    "Edited message is from before session start, not recording activity.",
                    message_id=update.edited_message.message_id,
                    session_start=active_session.session_start,
                )


async def on_message_react(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    """Handle reactions to messages."""
    if not update.message_reaction:
        raise NoMessageReactionError(update.update_id)

    with logfire.span(
        f"Processing message reaction on "
        f"message {update.message_reaction.message_id} in chat {update.effective_chat.id}",
        user_id=update.effective_user.id,
    ):
        async with async_database_session() as session:
            # Save the reaction
            await Messages.new_or_update(
                session,
                user_id=update.effective_user.id,
                chat_id=update.effective_chat.id,
                message=update.message_reaction,
            )

            # Handle session management for reactions
            active_session = await Sessions.get_active_session(session, str(update.effective_chat.id))

            if not active_session:
                logfire.debug("No active session found for message reaction, skipping session activity.")
                return

            # Only record user activity if the original message was sent after session start
            if update.message_reaction.date >= active_session.session_start:
                await active_session.new_activity(update.message_reaction.date, is_user=True)
                logfire.debug("Session activity recorded for message reaction.")
            else:
                logfire.debug(
                    "Message reaction is from before session start, not recording activity.",
                    message_id=update.message_reaction.message_id,
                    session_start=active_session.session_start,
                )
