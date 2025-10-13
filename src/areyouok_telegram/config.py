import os

from dotenv import load_dotenv

load_dotenv()

CONTROLLED_ENV = ["staging", "production"]
ENV = os.getenv("ENV", "development")

GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
GITHUB_SHA = os.getenv("GITHUB_SHA")

LOGFIRE_TOKEN = os.getenv("LOGFIRE_TOKEN")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Encryption salt for user keys - should be a secure random string
USER_ENCRYPTION_SALT = os.getenv("USER_ENCRYPTION_SALT", "default-salt")

PG_CONNECTION_STRING = os.getenv("PG_CONNECTION_STRING")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TINYURL_API_KEY = os.getenv("TINYURL_API_KEY")

DEVELOPER_CHAT_ID = os.getenv("DEVELOPER_CHAT_ID")
DEVELOPER_THREAD_ID = os.getenv("DEVELOPER_THREAD_ID")
CHAT_SESSION_TIMEOUT_MINS = int(os.getenv("CHAT_SESSION_TIMEOUT_MINS", "60"))  # Default to 60 minutes
LOG_CHAT_MESSAGES = os.getenv("LOG_CHAT_MESSAGES", "false").lower() in ("true", "1", "yes")

# Simulation mode - when enabled, disables database dependencies
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "false").lower() in ("true", "1", "yes")

# RAG Configuration
RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small")
RAG_EMBEDDING_DIMENSIONS = int(os.getenv("RAG_EMBEDDING_DIMENSIONS", "1536"))
RAG_BATCH_SIZE = int(os.getenv("RAG_BATCH_SIZE", "100"))
RAG_JOB_INTERVAL_SECS = int(os.getenv("RAG_JOB_INTERVAL_SECS", "300"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "30"))

# Profile Generation Configuration
PROFILE_JOB_INTERVAL_SECS = int(os.getenv("PROFILE_JOB_INTERVAL_SECS", "3600"))  # Default to hourly
