import asyncio

import telegram
import uvloop
from telegram.ext import ApplicationBuilder
from telegram.ext import MessageHandler
from telegram.ext import TypeHandler
from telegram.ext import filters

from areyouok_telegram.config import TELEGRAM_BOT_TOKEN
from areyouok_telegram.handlers import on_edit_message
from areyouok_telegram.handlers import on_error_event
from areyouok_telegram.handlers import on_new_message
from areyouok_telegram.handlers import on_new_update
from areyouok_telegram.lifecycle import database_setup
from areyouok_telegram.lifecycle import logging_setup

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


if __name__ == "__main__":
    # Setup logging configuration
    logging_setup()

    # Setup the database connection and tables
    database_setup()

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(concurrent_updates=True).build()

    application.add_error_handler(on_error_event)

    application.add_handler(TypeHandler(telegram.Update, on_new_update, block=True), group=0)

    application.add_handler(MessageHandler(filters.UpdateType.MESSAGE, on_new_message, block=False), group=1)
    application.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, on_edit_message, block=False), group=1)

    application.run_polling()
