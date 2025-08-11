import os

from dotenv import load_dotenv

load_dotenv()

CONTROLLED_ENV = ["staging", "production", "staging", "research"]
ENV = os.getenv("ENV", "development")

# Encryption salt for user keys - should be a secure random string
USER_ENCRYPTION_SALT = os.getenv("USER_ENCRYPTION_SALT", "default-salt")

GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
GITHUB_SHA = os.getenv("GITHUB_SHA")

LOGFIRE_TOKEN = os.getenv("LOGFIRE_TOKEN")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEVELOPER_CHAT_ID = os.getenv("DEVELOPER_CHAT_ID")

PG_CONNECTION_STRING = os.getenv("PG_CONNECTION_STRING")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

TINYURL_API_KEY = os.getenv("TINYURL_API_KEY")

CHAT_SESSION_TIMEOUT_MINS = int(os.getenv("CHAT_SESSION_TIMEOUT_MINS", "60"))  # Default to 60 minutes
LOG_CHAT_MESSAGES = os.getenv("LOG_CHAT_MESSAGES", "false").lower() in ("true", "1", "yes")

FEEDBACK_URL = os.getenv("FEEDBACK_URL", "NO_FEEDBACK_URL")
SESSION_ID_FIELD = os.getenv("SESSION_ID_FIELD", "NO_SESSION_ID_FIELD")
METADATA_FIELD = os.getenv("METADATA_FIELD", "NO_METADATA_FIELD")
FORM_NUM_PAGES = int(os.getenv("FORM_NUM_PAGES", "3"))  # Default to 3 pages
