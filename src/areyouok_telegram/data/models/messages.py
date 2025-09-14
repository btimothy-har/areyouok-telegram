from __future__ import annotations

import hashlib
import json
from datetime import UTC
from datetime import datetime

import telegram
from cachetools import TTLCache
from cryptography.fernet import Fernet
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.encryption.exceptions import ContentNotDecryptedError
from areyouok_telegram.logging import traced

MessageTypes = telegram.Message | telegram.MessageReactionUpdated


class InvalidMessageTypeError(Exception):
    def __init__(self, message_type: str):
        super().__init__(f"Invalid message type: {message_type}. Expected 'Message' or 'MessageReactionUpdated'.")
        self.message_type = message_type


class Messages(Base):
    __tablename__ = "messages"
    __table_args__ = {"schema": ENV}

    message_key = Column(String, nullable=False, unique=True)

    message_id = Column(String, nullable=False)
    message_type = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    chat_id = Column(String, nullable=False)
    encrypted_payload = Column(String, nullable=False)
    encrypted_reasoning = Column(Text, nullable=True)  # Store AI reasoning, encrypted

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Associate with a session key if needed
    session_key = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    # TTL cache for decrypted payload (1 hour TTL, max 1000 entries)
    _data_cache: TTLCache[str, str] = TTLCache(maxsize=1000, ttl=1 * 60 * 60)
    # TTL cache for decrypted reasoning (1 hour TTL, max 1000 entries)
    _reasoning_cache: TTLCache[str, str] = TTLCache(maxsize=1000, ttl=1 * 60 * 60)

    @staticmethod
    def generate_message_key(user_id: str, chat_id: str, message_id: int, message_type: str) -> str:
        """Generate a unique key for a message based on user ID, chat ID, message ID, and message type."""
        return hashlib.sha256(f"{user_id}:{chat_id}:{message_id}:{message_type}".encode()).hexdigest()

    @property
    def message_type_obj(self) -> type[MessageTypes]:
        """Return the class type of the message based on its type string."""
        if self.message_type == "MessageReactionUpdated":
            return telegram.MessageReactionUpdated
        elif self.message_type == "Message":
            return telegram.Message
        else:
            raise InvalidMessageTypeError(self.message_type)

    @classmethod
    def encrypt(cls, content: dict | str, user_encryption_key: str) -> str:
        """Encrypt content using the user's encryption key.

        Args:
            content: The content to encrypt (dict for payload, str for reasoning)
            user_encryption_key: The user's Fernet encryption key

        Returns:
            str: The encrypted content as base64-encoded string
        """
        fernet = Fernet(user_encryption_key.encode())

        # Convert dict to JSON string if needed
        if isinstance(content, dict):
            content_str = json.dumps(content)
        else:
            content_str = content

        encrypted_bytes = fernet.encrypt(content_str.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, user_encryption_key: str) -> None:
        """Decrypt both payload and reasoning using the user's encryption key and cache them.

        Args:
            user_encryption_key: The user's Fernet encryption key

        Raises:
            ValueError: If the encryption key format is invalid
            InvalidToken: If the encryption key is wrong or data is corrupted
        """
        fernet = Fernet(user_encryption_key.encode())

        # Decrypt payload if present and not already cached
        if self.encrypted_payload and self.message_key not in self._data_cache:
            encrypted_bytes = self.encrypted_payload.encode("utf-8")
            decrypted_bytes = fernet.decrypt(encrypted_bytes)
            payload_json = decrypted_bytes.decode("utf-8")
            self._data_cache[self.message_key] = payload_json

        # Decrypt reasoning if present and not already cached
        if self.encrypted_reasoning and self.message_key not in self._reasoning_cache:
            encrypted_bytes = self.encrypted_reasoning.encode("utf-8")
            decrypted_bytes = fernet.decrypt(encrypted_bytes)
            reasoning_text = decrypted_bytes.decode("utf-8")
            self._reasoning_cache[self.message_key] = reasoning_text

    @property
    def reasoning(self) -> str | None:
        """Get the decrypted reasoning from cache.

        Returns:
            str | None: The decrypted reasoning text, or None if not cached

        Raises:
            ContentNotDecryptedError: If reasoning hasn't been decrypted yet
        """
        if self.encrypted_reasoning and self.message_key not in self._reasoning_cache:
            raise ContentNotDecryptedError(self.message_key)
        return self._reasoning_cache.get(self.message_key)

    @property
    def telegram_object(self) -> MessageTypes | None:
        """Convert the database record to a Telegram message object using cached payload.

        Returns:
            MessageTypes | None: The Telegram object, or None if message is deleted.

        Raises:
            ContentNotDecryptedError: If payload hasn't been decrypted yet
        """
        payload_json = self._data_cache.get(self.message_key)
        if payload_json is None:
            raise ContentNotDecryptedError(self.message_key)

        payload_dict = json.loads(payload_json)
        return self.message_type_obj.de_json(payload_dict, None)

    @classmethod
    @traced(extract_args=["user_id", "chat_id", "message"])
    async def new_or_update(
        cls,
        db_conn: AsyncSession,
        *,
        user_encryption_key: str,
        user_id: str,
        chat_id: str,
        message: MessageTypes,
        session_key: str | None = None,
        reasoning: str | None = None,
    ):
        """Insert or update a message in the database with encrypted payload.

        Args:
            db_conn: Database connection
            user_encryption_key: The user's encryption key
            user_id: User ID
            chat_id: Chat ID
            message: Telegram message object
            session_key: Optional session key
            reasoning: Optional AI reasoning for bot messages
        """
        now = datetime.now(UTC)

        if not isinstance(message, MessageTypes):
            raise InvalidMessageTypeError(type(message).__name__)

        message_key = cls.generate_message_key(user_id, chat_id, message.message_id, message.__class__.__name__)

        # Encrypt the payload
        encrypted_payload = cls.encrypt(message.to_dict(), user_encryption_key)

        # Encrypt reasoning if provided
        encrypted_reasoning = cls.encrypt(reasoning, user_encryption_key) if reasoning else None

        stmt = pg_insert(cls).values(
            message_key=message_key,
            message_id=str(message.message_id),
            message_type=message.__class__.__name__,
            user_id=str(user_id),
            chat_id=str(chat_id),
            encrypted_payload=encrypted_payload,
            encrypted_reasoning=encrypted_reasoning,
            session_key=session_key,
            created_at=now,
            updated_at=now,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["message_key"],
            set_={
                "encrypted_payload": stmt.excluded.encrypted_payload,
                "encrypted_reasoning": stmt.excluded.encrypted_reasoning,
                "updated_at": stmt.excluded.updated_at,
            },
        )

        await db_conn.execute(stmt)

    @classmethod
    @traced(extract_args=["message_id", "chat_id"])
    async def retrieve_message_by_id(
        cls,
        db_conn: AsyncSession,
        *,
        message_id: str,
        chat_id: str,
        include_reactions: bool = True,
    ) -> tuple[Messages | None, list[Messages] | None]:
        """Retrieve a message by its ID and chat ID, returning SQLAlchemy Messages objects.

        Args:
            db_conn: Database connection
            message_id: The message ID to retrieve
            chat_id: The chat ID
            include_reactions: Whether to include reactions

        Returns:
            Tuple of (message, reactions) where both are SQLAlchemy Messages objects
        """
        stmt = select(cls).where(
            cls.message_id == message_id,
            cls.chat_id == chat_id,
            cls.message_type == "Message",
        )

        result = await db_conn.execute(stmt)
        message = result.scalar_one_or_none()

        reactions: list[Messages] = []

        if message and include_reactions:
            stmt = select(cls).where(
                cls.message_id == message_id,
                cls.chat_id == chat_id,
                cls.message_type == "MessageReactionUpdated",
            )
            reaction_result = await db_conn.execute(stmt)
            reactions = list(reaction_result.scalars().all())

        return message, reactions if include_reactions else None

    @classmethod
    @traced(extract_args=["session_id"])
    async def retrieve_by_session(
        cls,
        db_conn: AsyncSession,
        *,
        session_id: str,
    ) -> list[Messages]:
        """Retrieve messages by session_id, returning SQLAlchemy Messages models."""
        stmt = (
            select(cls)
            .where(
                cls.session_key == session_id,
            )
            .order_by(cls.created_at)
        )

        result = await db_conn.execute(stmt)
        messages = result.scalars().all()

        return list(messages)
