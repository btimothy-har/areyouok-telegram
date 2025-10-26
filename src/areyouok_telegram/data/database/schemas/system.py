"""System schemas for command tracking and job state."""

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

from areyouok_telegram.config import ENV
from areyouok_telegram.data.database import Base


class CommandUsageTable(Base):
    """Track command usage."""

    __tablename__ = "command_usage"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Unique identifier
    object_key = Column(String, nullable=False, unique=True, index=True)

    # Foreign keys
    chat_id = Column(Integer, ForeignKey(f"{ENV}.chats.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey(f"{ENV}.sessions.id"), nullable=True, index=True)

    # Command data
    command = Column(String, nullable=False)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False)


class JobStateTable(Base):
    """Store persistent state for background jobs."""

    __tablename__ = "job_state"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Unique identifier
    object_key = Column(String, nullable=False, unique=True, index=True)

    # Job identification
    job_name = Column(String, nullable=False, unique=True, index=True)

    # JSON state data - flexible schema for different job types
    state_data = Column(JSONB, nullable=False, default={})

    # Metadata
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)


class UpdatesTable(Base):
    """Store raw Telegram updates."""

    __tablename__ = "updates"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Unique identifier
    object_key = Column(String, nullable=False, unique=True, index=True)

    # Telegram update ID
    telegram_update_id = Column(BigInteger, nullable=False, index=True)

    # Update payload
    payload = Column(JSONB, nullable=False)

    # Metadata
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)


class NotificationsTable(Base):
    """Pending notifications for users."""

    __tablename__ = "notifications"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Unique identifier
    object_key = Column(String, nullable=False, unique=True, index=True)

    # Foreign key to chats
    chat_id = Column(Integer, ForeignKey(f"{ENV}.chats.id"), nullable=False, index=True)

    # Notification data
    content = Column(String, nullable=False)
    priority = Column(Integer, nullable=False, default=2)

    # Metadata
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)
    processed_at = Column(TIMESTAMP(timezone=True), nullable=True)
