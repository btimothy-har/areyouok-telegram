"""Core schemas for users, chats, and user metadata."""

from sqlalchemy import BOOLEAN, Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP

from areyouok_telegram.config import ENV
from areyouok_telegram.data.database import Base


class UsersTable(Base):
    """Lookup table mapping Telegram users to internal IDs."""

    __tablename__ = "users"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Unique identifiers
    object_key = Column(String, nullable=False, unique=True, index=True)
    telegram_user_id = Column(Integer, nullable=False, unique=True, index=True)

    # User attributes
    is_bot = Column(BOOLEAN, nullable=False)
    language_code = Column(String, nullable=True)
    is_premium = Column(BOOLEAN, nullable=False, default=False)

    # Metadata
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)


class ChatsTable(Base):
    """Lookup table mapping Telegram chats to internal IDs."""

    __tablename__ = "chats"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Unique identifiers
    object_key = Column(String, nullable=False, unique=True, index=True)
    telegram_chat_id = Column(Integer, nullable=False, unique=True, index=True)

    # Encryption key for chat data
    encrypted_key = Column(String, nullable=True)

    # Chat attributes
    type = Column(String, nullable=False)
    title = Column(String, nullable=True)
    is_forum = Column(BOOLEAN, nullable=False)

    # Metadata
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)


class UserMetadataTable(Base):
    """User metadata and preferences stored as encrypted JSON."""

    __tablename__ = "user_metadata"
    __table_args__ = {"schema": ENV}

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to users
    user_id = Column(Integer, ForeignKey(f"{ENV}.users.id"), nullable=False, unique=True, index=True)

    # Unique identifier
    object_key = Column(String, nullable=False, unique=True, index=True)

    # Encrypted metadata content
    content = Column(String, nullable=True)

    # Metadata
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)
