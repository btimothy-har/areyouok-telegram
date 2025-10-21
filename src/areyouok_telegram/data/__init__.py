"""Data layer with database connection and models."""

from areyouok_telegram.data.database import Base, async_database, async_engine
from areyouok_telegram.data.embeddings import context_doc_store, context_vector_index, context_vector_store
from areyouok_telegram.data.models import (
    SYSTEM_USER_ID,
    Chat,
    ChatEvent,
    CommandUsage,
    Context,
    ContextType,
    GuidedSession,
    GuidedSessionType,
    JobState,
    JournalContextMetadata,
    LLMGeneration,
    LLMUsage,
    MediaFile,
    Message,
    MessageTypes,
    Notification,
    Session,
    Update,
    User,
    UserMetadata,
)

__all__ = [
    # Database
    "async_database",
    "async_engine",
    "Base",
    # Embeddings
    "context_vector_store",
    "context_vector_index",
    "context_doc_store",
    # Core Models
    "User",
    "Chat",
    "UserMetadata",
    # Messaging Models
    "Message",
    "MessageTypes",
    "MediaFile",
    "Update",
    "Notification",
    # Session Models
    "Session",
    "Context",
    "ContextType",
    "GuidedSession",
    "GuidedSessionType",
    "JournalContextMetadata",
    # LLM Models
    "LLMUsage",
    "LLMGeneration",
    # System Models
    "CommandUsage",
    "JobState",
    # Helper Models
    "ChatEvent",
    "SYSTEM_USER_ID",
]
