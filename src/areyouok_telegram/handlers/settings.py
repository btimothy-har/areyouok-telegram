import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data import async_database
from areyouok_telegram.data import operations as data_operations
from areyouok_telegram.handlers.constants import MD2_SETTINGS_DISPLAY_TEMPLATE
from areyouok_telegram.llms.agent_settings import SettingsAgentDependencies
from areyouok_telegram.llms.agent_settings import SettingsUpdateResponse
from areyouok_telegram.llms.agent_settings import settings_agent
from areyouok_telegram.llms.utils import run_agent_with_tracking
from areyouok_telegram.logging import traced
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import escape_markdown_v2
from areyouok_telegram.utils import telegram_call


@traced(extract_args=["update"])
@db_retry()
async def on_settings_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
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
            return await telegram_call(
                context.bot.send_message,
                chat_id=update.effective_chat.id,
                text="Invalid field. Please specify one of: name, country, timezone.",
            )

        # Normalize field name: "name" -> "preferred_name"
        normalized_field_name = "preferred_name" if field_arg == "name" else field_arg

        await telegram_call(
            context.bot.set_message_reaction,
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            reaction="👌",
        )

        await telegram_call(
            context.bot.send_chat_action,
            chat_id=update.effective_chat.id,
            action=telegram.constants.ChatAction.TYPING,
        )

        active_session = await data_operations.get_or_create_active_session(
            chat_id=str(update.effective_chat.id),
            timestamp=update.message.date,
        )

        update_outcome = await _update_user_metadata_field(
            chat_id=str(update.effective_chat.id),
            session_id=str(active_session.session_id),
            field_name=normalized_field_name,
            new_value=text_input,
        )

        await telegram_call(
            context.bot.send_message,
            chat_id=update.effective_chat.id,
            text=update_outcome.feedback or "Settings updated successfully.",
        )

    else:
        user_settings_text = await _construct_user_settings_response(user_id=str(update.effective_user.id))

        await telegram_call(
            context.bot.send_message,
            chat_id=update.effective_chat.id,
            text=user_settings_text,
            parse_mode="MarkdownV2",
        )


async def _update_user_metadata_field(
    *,
    chat_id: str,
    session_id: str,
    field_name: str,
    new_value: str,
) -> SettingsUpdateResponse:
    update_instruction = f"Update {field_name} to {new_value}."

    update = await run_agent_with_tracking(
        settings_agent,
        chat_id=chat_id,
        session_id=session_id,
        run_kwargs={
            "user_prompt": update_instruction,
            "deps": SettingsAgentDependencies(
                tg_chat_id=chat_id,
                tg_session_id=session_id,
            ),
        },
    )
    update_outcome: SettingsUpdateResponse = update.output

    return update_outcome


@db_retry()
async def _construct_user_settings_response(user_id: str):
    async with async_database() as db_conn:
        # Get user metadata
        user_metadata = await UserMetadata.get_by_user_id(
            db_conn,
            user_id=user_id,
        )

        # Format settings display
        if user_metadata:
            name = user_metadata.preferred_name or "Not set"
            country = user_metadata.country_display_name or "Not set"
            timezone = user_metadata.timezone or "Not set"
            response_speed = user_metadata.response_speed or "Not set"

            # Handle "rather_not_say" values for timezone
            if timezone == "rather_not_say":
                timezone = "Prefer not to say"
        else:
            name = "Not set"
            country = "Not set"
            timezone = "Not set"
            response_speed = "Not set"

        settings_text = MD2_SETTINGS_DISPLAY_TEMPLATE.format(
            name=escape_markdown_v2(name),
            country=escape_markdown_v2(country),
            timezone=escape_markdown_v2(timezone),
            response_speed=escape_markdown_v2(response_speed),
        )

    return settings_text
