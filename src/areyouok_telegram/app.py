"""Application factory for the Telegram bot."""

import telegram
from telegram.ext import Application
from telegram.ext import ApplicationBuilder
from telegram.ext import CommandHandler
from telegram.ext import MessageHandler
from telegram.ext import MessageReactionHandler
from telegram.ext import TypeHandler
from telegram.ext import filters

from areyouok_telegram.config import TELEGRAM_BOT_TOKEN
from areyouok_telegram.handlers import commands as commands_handlers
from areyouok_telegram.handlers import on_edit_message
from areyouok_telegram.handlers import on_error_event
from areyouok_telegram.handlers import on_message_react
from areyouok_telegram.handlers import on_new_message
from areyouok_telegram.handlers import on_new_update
from areyouok_telegram.logging import traced
from areyouok_telegram.setup import restore_active_sessions
from areyouok_telegram.setup import setup_bot_commands
from areyouok_telegram.setup import setup_bot_description
from areyouok_telegram.setup import setup_bot_name
from areyouok_telegram.setup import setup_bot_short_description
from areyouok_telegram.setup import start_data_warning_job
from areyouok_telegram.setup import start_ping_job


async def application_post_init(application: Application):
    """Configure bot metadata on startup."""
    await setup_bot_name(application)
    await setup_bot_description(application)
    await setup_bot_short_description(application)
    await restore_active_sessions(application)
    await start_data_warning_job(application)
    await start_ping_job(application)
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

    # Command Handlers
    application.add_handler(CommandHandler("start", commands_handlers.on_start_command, block=False), group=1)
    application.add_handler(CommandHandler("settings", commands_handlers.on_settings_command, block=False), group=1)
    application.add_handler(CommandHandler("end", commands_handlers.on_end_command, block=False), group=1)

    # Message Handlers
    application.add_handler(MessageHandler(filters.UpdateType.MESSAGE, on_new_message, block=False), group=1)
    application.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, on_edit_message, block=False), group=1)

    # Reaction Handler
    application.add_handler(MessageReactionHandler(on_message_react, message_reaction_types=-1, block=False), group=1)

    return application
