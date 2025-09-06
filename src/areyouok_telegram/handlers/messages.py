import asyncio

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import Chats
from areyouok_telegram.data import GuidedSessions
from areyouok_telegram.data import Messages
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.handlers.exceptions import NoEditedMessageError
from areyouok_telegram.handlers.exceptions import NoMessageError
from areyouok_telegram.handlers.exceptions import NoMessageReactionError
from areyouok_telegram.handlers.media_utils import extract_media_from_telegram_message
from areyouok_telegram.handlers.media_utils import handle_unsupported_media
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import telegram_call
from areyouok_telegram.utils import traced


@traced(extract_args=["update"])
@db_retry()
async def on_new_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.message:
        raise NoMessageError(update.update_id)

    async with async_database() as db_conn:
        # Get chat and its encryption key
        chat_obj = await Chats.get_by_id(db_conn, chat_id=str(update.effective_chat.id))
        chat_encryption_key = chat_obj.retrieve_key()

        # Handle session management
        chat_id = str(update.effective_chat.id)
        active_session = await Sessions.get_active_session(db_conn, chat_id=chat_id)

        if not active_session:
            active_session = await Sessions.create_session(
                db_conn,
                chat_id=chat_id,
                timestamp=update.message.date,
            )
        else:
            chk_onboarding = await GuidedSessions.get_by_chat_session(
                db_conn,
                chat_session=active_session.session_id,
                session_type="onboarding",
            )

            if chk_onboarding:
                await telegram_call(
                    context.bot.send_chat_action,
                    chat_id=update.effective_chat.id,
                    action=telegram.constants.ChatAction.TYPING,
                )

        extract_media = asyncio.create_task(
            extract_media_from_telegram_message(
                db_conn,
                chat_encryption_key,
                message=update.message,
                session_id=active_session.session_id,
            )
        )

        # Save the message
        await Messages.new_or_update(
            db_conn,
            user_encryption_key=chat_encryption_key,
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            message=update.message,
            session_key=active_session.session_key,
        )
        await active_session.new_message(
            db_conn,
            timestamp=update.message.date,
            is_user=True,
        )
        media_count = await extract_media

        # Check for unsupported media and create notifications if media was found
        if media_count > 0:
            await handle_unsupported_media(
                db_conn,
                chat_id=str(update.effective_chat.id),
                message_id=str(update.message.message_id),
            )


@traced(extract_args=["update"])
@db_retry()
async def on_edit_message(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    if not update.edited_message:
        raise NoEditedMessageError(update.update_id)

    async with async_database() as db_conn:
        # Get chat and its encryption key
        chat_obj = await Chats.get_by_id(db_conn, chat_id=str(update.effective_chat.id))
        chat_encryption_key = chat_obj.retrieve_key()

        # Handle session management for edits
        active_session = await Sessions.get_active_session(db_conn, str(update.effective_chat.id))
        edit_is_part_of_session = (
            update.edited_message.date >= active_session.session_start if active_session else False
        )

        extract_media = asyncio.create_task(
            extract_media_from_telegram_message(
                db_conn,
                chat_encryption_key,
                message=update.edited_message,
                session_id=active_session.session_id if edit_is_part_of_session else None,
            )
        )

        await Messages.new_or_update(
            db_conn,
            user_encryption_key=chat_encryption_key,
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            message=update.edited_message,
            session_key=active_session.session_key if edit_is_part_of_session else None,
        )

        # Only record user activity if the original message was sent after session start
        if edit_is_part_of_session:
            await active_session.new_activity(
                db_conn=db_conn,
                timestamp=update.edited_message.edit_date or update.edited_message.date,
                is_user=True,
            )

        media_count = await extract_media

        # Check for unsupported media and create notifications if media was found
        if media_count > 0:
            await handle_unsupported_media(
                db_conn,
                chat_id=str(update.effective_chat.id),
                message_id=str(update.edited_message.message_id),
            )


@traced(extract_args=["update"])
@db_retry()
async def on_message_react(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    """Handle reactions to messages."""
    if not update.message_reaction:
        raise NoMessageReactionError(update.update_id)

    async with async_database() as db_conn:
        # Get chat and its encryption key
        chat_obj = await Chats.get_by_id(db_conn, chat_id=str(update.effective_chat.id))
        chat_encryption_key = chat_obj.retrieve_key()

        # Handle session management for reactions
        active_session = await Sessions.get_active_session(db_conn, str(update.effective_chat.id))
        react_is_part_of_session = (
            update.message_reaction.date >= active_session.session_start if active_session else False
        )

        # Save the reaction
        await Messages.new_or_update(
            db_conn,
            user_encryption_key=chat_encryption_key,
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            message=update.message_reaction,
            session_key=active_session.session_key if react_is_part_of_session else None,
        )

        # Only record user activity if the original message was sent after session start
        if react_is_part_of_session:
            await active_session.new_activity(
                db_conn=db_conn,
                timestamp=update.message_reaction.date,
                is_user=True,
            )
