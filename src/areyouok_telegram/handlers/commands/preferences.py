import pycountry
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data.models import Chat, CommandUsage, Session, User, UserMetadata
from areyouok_telegram.handlers.exceptions import NoChatFoundError, NoUserFoundError
from areyouok_telegram.handlers.utils.constants import MD2_PREFERENCES_DISPLAY_TEMPLATE
from areyouok_telegram.llms import run_agent_with_tracking
from areyouok_telegram.llms.agent_preferences import (
    PreferencesAgentDependencies,
    PreferencesUpdateResponse,
    preferences_agent,
)
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import telegram_call
from areyouok_telegram.utils.text import escape_markdown_v2


@traced(extract_args=["update"])
async def on_preferences_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /preferences command - display user's current preferences."""

    chat = await Chat.get_by_id(telegram_chat_id=update.effective_chat.id)
    if not chat:
        raise NoChatFoundError(update.effective_chat.id)

    user = await User.get_by_id(telegram_user_id=update.effective_user.id)
    if not user:
        raise NoUserFoundError(update.effective_user.id)

    # Get active session up front
    active_session = await Session.get_or_create_new_session(
        chat=chat,
        session_start=update.message.date,
    )

    # Track command usage
    command_usage = CommandUsage(
        chat=chat,
        command="preferences",
        session_id=active_session.id,
        timestamp=update.message.date,
    )
    await command_usage.save()

    command_input = update.message.text

    # Parse command arguments: /preferences [field_arg] [text_input]
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

        # Update user metadata field via LLM agent
        update_instruction = f"Update {normalized_field_name} to {text_input}."
        update_result = await run_agent_with_tracking(
            preferences_agent,
            chat_id=chat.id,
            session_id=active_session.id,
            run_kwargs={
                "user_prompt": update_instruction,
                "deps": PreferencesAgentDependencies(
                    tg_chat_id=chat.telegram_chat_id,
                    tg_session_id=active_session.id,
                ),
            },
        )
        update_outcome: PreferencesUpdateResponse = update_result.output

        await telegram_call(
            context.bot.send_message,
            chat_id=update.effective_chat.id,
            text=update_outcome.feedback or "Settings updated successfully.",
        )

    else:
        # Get user metadata
        user_metadata = await UserMetadata.get_by_user_id(user_id=user.id)

        # Format settings display
        if user_metadata:
            name = user_metadata.preferred_name or "Not set"

            if not user_metadata.country:
                country = "Not set"
            elif user_metadata.country == "rather_not_say":
                country = "Prefer not to say"
            else:
                country = pycountry.countries.get(alpha_3=user_metadata.country).name

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

        preferences_text = MD2_PREFERENCES_DISPLAY_TEMPLATE.format(
            name=escape_markdown_v2(name),
            country=escape_markdown_v2(country),
            timezone=escape_markdown_v2(timezone),
            response_speed=escape_markdown_v2(response_speed),
        )

        await telegram_call(
            context.bot.send_message,
            chat_id=update.effective_chat.id,
            text=preferences_text,
            parse_mode="MarkdownV2",
        )
