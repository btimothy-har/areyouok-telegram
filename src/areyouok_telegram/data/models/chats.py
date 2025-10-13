import hashlib
from datetime import UTC, datetime

import telegram
from cachetools import TTLCache
from sqlalchemy import BOOLEAN, Column, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.encryption import decrypt_chat_key, encrypt_chat_key, generate_chat_key
from areyouok_telegram.logging import traced


class Chats(Base):
    __tablename__ = "chats"
    __table_args__ = {"schema": ENV}

    chat_key = Column(String, nullable=False, unique=True)
    encrypted_key = Column(String, nullable=True)

    chat_id = Column(String, nullable=False)
    type = Column(String, nullable=False)
    title = Column(String, nullable=True)
    is_forum = Column(BOOLEAN, nullable=False)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    # TTL cache for decrypted keys (10 minutes TTL, max 1000 entries)
    _key_cache: TTLCache[str, str] = TTLCache(maxsize=1000, ttl=10 * 60)

    @staticmethod
    def generate_chat_key_hash(chat_id: str) -> str:
        """Generate a unique key for a chat based on its chat ID."""
        return hashlib.sha256(f"{chat_id}".encode()).hexdigest()

    def retrieve_key(self) -> str | None:
        """Retrieve the chat's encryption key.

        Returns:
            str: The decrypted Fernet key, or None if no key is stored

        Raises:
            InvalidToken: If the key cannot be decrypted (corrupted data)
        """
        if not self.encrypted_key:
            return None

        # Check cache first
        if self.chat_key in self._key_cache:
            return self._key_cache[self.chat_key]

        # Decrypt the key and cache it
        decrypted_key = decrypt_chat_key(self.encrypted_key)
        self._key_cache[self.chat_key] = decrypted_key
        return decrypted_key

    @classmethod
    async def get_by_id(cls, db_conn: AsyncSession, *, chat_id: str) -> "Chats | None":
        """Retrieve a chat by its ID."""
        stmt = select(cls).where(cls.chat_id == chat_id)
        result = await db_conn.execute(stmt)
        return result.scalars().first()

    @classmethod
    @traced(extract_args=["chat"])
    async def new_or_update(cls, db_conn: AsyncSession, *, chat: telegram.Chat) -> "Chats":
        """Insert or update a chat in the database and return the Chat object."""
        now = datetime.now(UTC)

        # Check if chat already exists
        existing_chat = await cls.get_by_id(db_conn, chat_id=str(chat.id))

        encrypted_key = None
        if not existing_chat:
            # Generate a new Fernet key for the chat
            new_key = generate_chat_key()
            # Encrypt it using the application salt
            encrypted_key = encrypt_chat_key(new_key)

        stmt = pg_insert(cls).values(
            chat_key=cls.generate_chat_key_hash(str(chat.id)),
            encrypted_key=encrypted_key,
            chat_id=str(chat.id),
            type=chat.type,
            title=chat.title,
            is_forum=chat.is_forum if chat.is_forum is not None else False,
            created_at=now,
            updated_at=now,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["chat_key"],
            set_={
                "type": stmt.excluded.type,
                "title": stmt.excluded.title,
                "is_forum": stmt.excluded.is_forum,
                "updated_at": stmt.excluded.updated_at,
                # Don't update encrypted_key if chat already exists
            },
        )

        await db_conn.execute(stmt)

        # Return the chat object after upsert
        return await cls.get_by_id(db_conn, chat_id=str(chat.id))
