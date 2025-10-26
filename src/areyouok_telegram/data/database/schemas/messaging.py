"""Messaging schemas for messages, media, updates, and notifications."""

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP

from areyouok_telegram.config import ENV
from areyouok_telegram.data.database import Base


class MessagesTable(Base):
    """Lookup table for Telegram messages and reactions."""

    __tablename__ = "messages"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Unique identifier
    object_key = Column(String, nullable=False, unique=True, index=True)

    # Foreign keys to lookup tables
    user_id = Column(Integer, ForeignKey(f"{ENV}.users.id"), nullable=False, index=True)
    chat_id = Column(Integer, ForeignKey(f"{ENV}.chats.id"), nullable=False, index=True)

    # Telegram identifier
    telegram_message_id = Column(BigInteger, nullable=False, index=True)

    # Message data
    message_type = Column(String, nullable=False)
    encrypted_payload = Column(String, nullable=False)
    encrypted_reasoning = Column(Text, nullable=True)

    # Session association (FK added later when sessions table exists)
    session_id = Column(Integer, nullable=True, index=True)

    # Metadata
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)


class MediaFilesTable(Base):
    """Store media files from messages in encrypted format."""

    __tablename__ = "media_files"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Unique identifier
    object_key = Column(String, nullable=False, unique=True, index=True)

    # Foreign keys
    chat_id = Column(Integer, ForeignKey(f"{ENV}.chats.id"), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey(f"{ENV}.messages.id"), nullable=False, index=True)

    # Telegram file identifiers
    file_id = Column(String, nullable=False, index=True)
    file_unique_id = Column(String, nullable=False, index=True)

    # File data
    mime_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    encrypted_content_base64 = Column(Text, nullable=False)

    # Metadata
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)
    last_accessed_at = Column(TIMESTAMP(timezone=True), nullable=True)
