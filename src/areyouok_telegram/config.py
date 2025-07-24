import os

from dotenv import load_dotenv

load_dotenv()

ENV = os.getenv("ENV", "development")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEVELOPER_CHAT_ID = os.getenv("DEVELOPER_CHAT_ID")

PG_CONNECTION_STRING = os.getenv("PG_CONNECTION_STRING")
