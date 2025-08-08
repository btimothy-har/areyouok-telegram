import os

from dotenv import load_dotenv

load_dotenv()

CONTROLLED_ENV = ["staging", "production", "staging", "research"]

ENV = os.getenv("ENV", "development")

GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
GITHUB_SHA = os.getenv("GITHUB_SHA")

LOGFIRE_TOKEN = os.getenv("LOGFIRE_TOKEN")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEVELOPER_CHAT_ID = os.getenv("DEVELOPER_CHAT_ID")

PG_CONNECTION_STRING = os.getenv("PG_CONNECTION_STRING")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

CHAT_SESSION_TIMEOUT_MINS = int(os.getenv("CHAT_SESSION_TIMEOUT", "60"))  # Default to 60 minutes
