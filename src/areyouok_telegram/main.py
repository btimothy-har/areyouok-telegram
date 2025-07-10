import asyncio

import uvloop
from telegram.ext import ApplicationBuilder

from areyouok_telegram.config import TELEGRAM_BOT_TOKEN


def main():
    print("Hello from areyouok-telegram!")
    print(TELEGRAM_BOT_TOKEN)


if __name__ == "__main__":
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    application = (
        ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(True).build()
    )

    application.run_polling()
