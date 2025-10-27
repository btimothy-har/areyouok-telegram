"""Session-related schemas for conversation tracking."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP

from areyouok_telegram.config import ENV
from areyouok_telegram.data.database import Base


class SessionsTable(Base):
    """Conversation sessions."""

    __tablename__ = "sessions"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Unique identifier
    object_key = Column(String, nullable=False, unique=True, index=True)

    # Foreign key to chats
    chat_id = Column(Integer, ForeignKey(f"{ENV}.chats.id"), nullable=False, index=True)

    # Session timing
    session_start = Column(TIMESTAMP(timezone=True), nullable=False)
    session_end = Column(TIMESTAMP(timezone=True), nullable=True)

    # Activity tracking
    last_user_message = Column(TIMESTAMP(timezone=True), nullable=True)
    last_user_activity = Column(TIMESTAMP(timezone=True), nullable=True)
    last_bot_message = Column(TIMESTAMP(timezone=True), nullable=True)
    last_bot_activity = Column(TIMESTAMP(timezone=True), nullable=True)

    # Message count
    message_count = Column(Integer, nullable=True)


class ContextTable(Base):
    """Session context and metadata."""

    __tablename__ = "context"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Unique identifier
    object_key = Column(String, nullable=False, unique=True, index=True)

    # Foreign keys
    chat_id = Column(Integer, ForeignKey(f"{ENV}.chats.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey(f"{ENV}.sessions.id"), nullable=True, index=True)

    # Context data
    type = Column(String, nullable=False, index=True)
    encrypted_content = Column(String, nullable=False)

    # Metadata
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)


class GuidedSessionsTable(Base):
    """Guided session progress tracking (onboarding, journaling, etc.)."""

    __tablename__ = "guided_sessions"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Unique identifier
    object_key = Column(String, nullable=False, unique=True, index=True)

    # Foreign keys
    chat_id = Column(Integer, ForeignKey(f"{ENV}.chats.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey(f"{ENV}.sessions.id"), nullable=False, index=True)

    # Session type and state
    session_type = Column(String, nullable=False, index=True)
    state = Column(String, nullable=False, default="incomplete")

    # Timing
    started_at = Column(TIMESTAMP(timezone=True), nullable=False)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Encrypted session-specific metadata
    encrypted_metadata = Column(Text, nullable=True)

    # Metadata
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)
