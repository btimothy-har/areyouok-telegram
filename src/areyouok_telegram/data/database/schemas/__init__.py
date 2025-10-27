"""SQLAlchemy table schemas organized by domain."""

from areyouok_telegram.data.database.schemas.core import ChatsTable, UserMetadataTable, UsersTable
from areyouok_telegram.data.database.schemas.llm import LLMGenerationsTable, LLMUsageTable
from areyouok_telegram.data.database.schemas.messaging import (
    MediaFilesTable,
    MessagesTable,
)
from areyouok_telegram.data.database.schemas.sessions import ContextTable, GuidedSessionsTable, SessionsTable
from areyouok_telegram.data.database.schemas.system import (
    CommandUsageTable,
    JobStateTable,
    NotificationsTable,
    UpdatesTable,
)

__all__ = [
    # Core
    "UsersTable",
    "ChatsTable",
    "UserMetadataTable",
    # Messaging
    "MessagesTable",
    "MediaFilesTable",
    # Sessions
    "SessionsTable",
    "ContextTable",
    "GuidedSessionsTable",
    # LLM
    "LLMUsageTable",
    "LLMGenerationsTable",
    # System
    "CommandUsageTable",
    "JobStateTable",
    "NotificationsTable",
    "UpdatesTable",
]
