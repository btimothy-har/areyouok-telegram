"""Pydantic models for the application data layer.

Models are organized by domain to match the database schema structure:
- Users: User, UserMetadata
- Messaging: Chat, Message, MediaFile, Session, Context, GuidedSession, ChatEvent
- LLM: LLMUsage, LLMGeneration
- System: CommandUsage, JobState, Notification, Update
"""

# Import from subdirectories
from areyouok_telegram.data.models.llm import LLMGeneration, LLMUsage
from areyouok_telegram.data.models.messaging import (
    SYSTEM_USER_ID,
    Chat,
    ChatEvent,
    Context,
    ContextType,
    GuidedSession,
    GuidedSessionType,
    JournalContextMetadata,
    MediaFile,
    Message,
    MessageTypes,
    Session,
)
from areyouok_telegram.data.models.system import CommandUsage, JobState, Notification, Update
from areyouok_telegram.data.models.users import (
    InvalidCountryCodeError,
    InvalidFieldValueError,
    InvalidTimezoneError,
    User,
    UserMetadata,
)

__all__ = [
    # Core
    "User",
    "Chat",
    "UserMetadata",
    "InvalidCountryCodeError",
    "InvalidFieldValueError",
    "InvalidTimezoneError",
    # Messaging
    "Message",
    "MessageTypes",
    "MediaFile",
    "Notification",
    # Sessions
    "Session",
    "Context",
    "ContextType",
    "GuidedSession",
    "GuidedSessionType",
    "JournalContextMetadata",
    # LLM
    "LLMUsage",
    "LLMGeneration",
    # System
    "CommandUsage",
    "JobState",
    # Helpers
    "Update",
    "ChatEvent",
    "SYSTEM_USER_ID",
]
