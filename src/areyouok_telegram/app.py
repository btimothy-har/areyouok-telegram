"""Application factory for the Telegram bot."""

import telegram
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    MessageReactionHandler,
    TypeHandler,
    filters,
)

from areyouok_telegram.config import TELEGRAM_BOT_TOKEN
from areyouok_telegram.handlers import (
    on_dynamic_response_callback,
    on_edit_message,
    on_error_event,
    on_feedback_command,
    on_journal_command,
    on_message_react,
    on_new_message,
    on_new_update,
    on_preferences_command,
    on_start_command,
)
from areyouok_telegram.logging import traced
from areyouok_telegram.setup import (
    restore_active_sessions,
    setup_bot_commands,
    setup_bot_description,
    setup_bot_name,
    setup_bot_short_description,
    start_context_embedding_job,
    start_data_warning_job,
    start_ping_job,
    start_profile_generation_job,
)


async def application_post_init(application: Application):
    """Configure bot metadata on startup."""
    await setup_bot_name(application)
    await setup_bot_description(application)
    await setup_bot_short_description(application)
    await restore_active_sessions(application)
    await start_data_warning_job(application)
    await start_ping_job(application)
    await start_context_embedding_job(application)
    await start_profile_generation_job(application)
    await setup_bot_commands(application)


@traced(extract_args=False)
def create_application() -> Application:
    """Create and configure the Telegram bot application."""

    # Create application
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(concurrent_updates=True)
        .post_init(application_post_init)
        .build()
    )

    # Add error handler
    application.add_error_handler(on_error_event)

    # Add handlers by group
    application.add_handler(TypeHandler(telegram.Update, on_new_update, block=True), group=0)

    # Callback Handlers
    application.add_handler(
        CallbackQueryHandler(on_dynamic_response_callback, pattern=r"^response::", block=False), group=1
    )

    # Command Handlers
    application.add_handler(CommandHandler("start", on_start_command, block=False), group=2)
    application.add_handler(CommandHandler("journal", on_journal_command, block=False), group=2)
    application.add_handler(CommandHandler("preferences", on_preferences_command, block=False), group=2)
    application.add_handler(CommandHandler("feedback", on_feedback_command, block=False), group=2)

    # Message Handlers
    application.add_handler(MessageHandler(filters.UpdateType.MESSAGE, on_new_message, block=False), group=2)
    application.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, on_edit_message, block=False), group=2)

    # Reaction Handler
    application.add_handler(MessageReactionHandler(on_message_react, message_reaction_types=-1, block=False), group=2)

    return application
