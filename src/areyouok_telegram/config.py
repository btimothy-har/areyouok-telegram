import os

ENV = os.getenv("ENV", "development")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

PG_CONNECTION_STRING = os.getenv("PG_CONNECTION_STRING")
