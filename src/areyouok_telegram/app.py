"""Application factory for the Telegram bot."""

import telegram
from telegram.ext import Application
from telegram.ext import ApplicationBuilder
from telegram.ext import MessageHandler
from telegram.ext import TypeHandler
from telegram.ext import filters

from areyouok_telegram.config import TELEGRAM_BOT_TOKEN
from areyouok_telegram.handlers import on_edit_message
from areyouok_telegram.handlers import on_error_event
from areyouok_telegram.handlers import on_new_message
from areyouok_telegram.handlers import on_new_update
from areyouok_telegram.setup import database_setup
from areyouok_telegram.setup import logging_setup
from areyouok_telegram.setup import setup_bot_description
from areyouok_telegram.setup import setup_bot_name


async def application_startup(application: Application):
    """Configure bot metadata on startup."""
    await setup_bot_name(application)
    await setup_bot_description(application)


def create_application() -> Application:
    """Create and configure the Telegram bot application."""
    # Initialize infrastructure
    logging_setup()
    database_setup()

    # Create application
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(concurrent_updates=True)
        .post_init(application_startup)
        .build()
    )

    # Add error handler
    application.add_error_handler(on_error_event)

    # Add handlers by group
    application.add_handler(TypeHandler(telegram.Update, on_new_update, block=True), group=0)
    application.add_handler(MessageHandler(filters.UpdateType.MESSAGE, on_new_message, block=False), group=1)
    application.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, on_edit_message, block=False), group=1)

    return application
