"""Main entry point for the Telegram bot application."""

import asyncio

import telegram
import uvloop

from areyouok_telegram.app import create_application

if __name__ == "__main__":
    # Configure event loop policy for performance
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    application = create_application()
    application.run_polling(allowed_updates=telegram.Update.ALL_TYPES, drop_pending_updates=True)
