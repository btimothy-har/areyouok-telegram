import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import Chats
from areyouok_telegram.data import GuidedSessions
from areyouok_telegram.data import GuidedSessionType
from areyouok_telegram.data import Messages
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.handlers.constants import ONBOARDING_COMPLETE_MESSAGE
from areyouok_telegram.handlers.constants import ONBOARDING_START_MESSAGE
from areyouok_telegram.handlers.settings_utils import construct_user_settings_response
from areyouok_telegram.handlers.settings_utils import update_user_metadata_field
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import traced


@traced(extract_args=["update"])
@db_retry()
async def on_start_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    async with async_database() as db_conn:
        # Get chat and its encryption key
        chat_obj = await Chats.get_by_id(db_conn, chat_id=str(update.effective_chat.id))
        chat_encryption_key = chat_obj.retrieve_key()

        # Handle session management
        chat_id = str(update.effective_chat.id)
        active_session = await Sessions.get_active_session(db_conn, chat_id=chat_id)

        if not active_session:
            active_session = await Sessions.create_session(db_conn, chat_id=chat_id, timestamp=update.message.date)

        # Check for existing onboarding sessions for this chat
        onboarding_sessions = await GuidedSessions.get_by_chat_id(
            db_conn,
            chat_id=str(update.effective_chat.id),
            session_type=GuidedSessionType.ONBOARDING.value,
        )

        # Get the most recent onboarding session (first in desc order)
        onboarding_session = onboarding_sessions[0] if onboarding_sessions else None

        if onboarding_session and onboarding_session.is_completed:
            return await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=ONBOARDING_COMPLETE_MESSAGE,
                parse_mode="MarkdownV2",
            )

        elif not onboarding_session or onboarding_session.is_incomplete:
            await GuidedSessions.start_new_session(
                db_conn,
                chat_id=str(update.effective_chat.id),
                chat_session=active_session.session_key,
                session_type=GuidedSessionType.ONBOARDING.value,
            )

        await Messages.new_or_update(
            db_conn,
            user_encryption_key=chat_encryption_key,
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            message=update.message,
            session_key=active_session.session_key,
        )
        await active_session.new_message(db_conn, timestamp=update.message.date, is_user=True)

        if not active_session.last_bot_activity:
            bot_message = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=ONBOARDING_START_MESSAGE,
                parse_mode="MarkdownV2",
            )

            await Messages.new_or_update(
                db_conn,
                user_encryption_key=chat_encryption_key,
                user_id="system",
                chat_id=str(update.effective_chat.id),
                message=bot_message,
                session_key=active_session.session_key,
            )


@traced(extract_args=["update"])
@db_retry()
async def on_end_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    return


@traced(extract_args=["update"])
@db_retry()
async def on_settings_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    """Handle /settings command - display user's current preferences."""

    command_input = update.message.text

    # Parse command arguments: /settings [field_arg] [text_input]
    command_parts = command_input.split(maxsplit=2)  # Split into max 3 parts
    field_arg = None
    text_input = None

    if len(command_parts) >= 2:
        field_arg = command_parts[1]
    if len(command_parts) >= 3:
        text_input = command_parts[2]

    if field_arg and text_input:
        if field_arg not in ["preferred_name", "name", "country", "timezone"]:
            return await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Invalid field. Please specify one of: name, country, timezone.",
            )

        # Normalize field name: "name" -> "preferred_name"
        normalized_field_name = "preferred_name" if field_arg == "name" else field_arg

        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=update.message.id,
            reaction="👌",
        )

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=telegram.constants.ChatAction.TYPING,
        )

        async with async_database() as db_conn:
            chat_id = str(update.effective_chat.id)
            active_session = await Sessions.get_active_session(db_conn, chat_id=chat_id)

            if not active_session:
                active_session = await Sessions.create_session(db_conn, chat_id=chat_id, timestamp=update.message.date)

        update_outcome = await update_user_metadata_field(
            chat_id=str(update.effective_chat.id),
            session_id=str(active_session.session_id),
            field_name=normalized_field_name,
            new_value=text_input,
        )

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=update_outcome.feedback,
        )

    else:
        user_settings_text = await construct_user_settings_response(user_id=str(update.effective_user.id))

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=user_settings_text,
            parse_mode="MarkdownV2",
        )
