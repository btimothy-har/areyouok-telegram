import hashlib
import json
from datetime import UTC
from datetime import datetime
from enum import Enum
from typing import Any

from cachetools import TTLCache
from cryptography.fernet import Fernet
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.encryption.exceptions import ContentNotDecryptedError
from areyouok_telegram.logging import traced


class ContextType(Enum):
    SESSION = "session"
    RESPONSE = "response"
    PERSONALITY = "personality"
    METADATA = "metadata"
    ACTION = "action"


VALID_CONTEXT_TYPES = [context_type.value for context_type in ContextType]


class InvalidContextTypeError(Exception):
    def __init__(self, context_type: str):
        super().__init__(f"Invalid context type: {context_type}. Expected one of: {VALID_CONTEXT_TYPES}.")
        self.context_type = context_type


class Context(Base):
    __tablename__ = "context"
    __table_args__ = {"schema": ENV}

    context_key = Column(String, nullable=False, unique=True)

    chat_id = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    type = Column(String, nullable=False)
    encrypted_content = Column(String, nullable=False)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)

    # TTL cache for decrypted content (1 hour TTL, max 1000 entries)
    _data_cache: TTLCache[str, bytes] = TTLCache(maxsize=1000, ttl=1 * 60 * 60)

    @staticmethod
    def generate_context_key(chat_id: str, ctype: str, encrypted_content: str) -> str:
        """Generate a unique key for a context based on chat ID, type, and encrypted content."""
        return hashlib.sha256(f"{chat_id}:{ctype}:{encrypted_content}".encode()).hexdigest()

    @classmethod
    def encrypt_content(cls, *, content: str, chat_encryption_key: str) -> str:
        """Encrypt the content using the user's encryption key.

        Args:
            content: The content string to encrypt
            chat_encryption_key: The user's Fernet encryption key

        Returns:
            str: The encrypted content as base64-encoded string
        """
        fernet = Fernet(chat_encryption_key.encode())
        encrypted_bytes = fernet.encrypt(content.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt_content(self, *, chat_encryption_key: str) -> str | None:
        """Decrypt the content using the user's encryption key.

        Args:
            chat_encryption_key: The user's Fernet encryption key

        Returns:
            str: The decrypted content string, or None if no encrypted content
        """
        if not self.encrypted_content:
            return None

        fernet = Fernet(chat_encryption_key.encode())
        encrypted_bytes = self.encrypted_content.encode("utf-8")
        decrypted_bytes = fernet.decrypt(encrypted_bytes)

        self._data_cache[self.context_key] = decrypted_bytes
        return decrypted_bytes.decode("utf-8")

    @property
    def content(self) -> Any:
        """Return the decrypted content from the cache."""
        decrypted_bytes = self._data_cache.get(self.context_key)
        if decrypted_bytes is None:
            raise ContentNotDecryptedError(self.context_key)

        return json.loads(decrypted_bytes.decode("utf-8"))

    @classmethod
    @traced(extract_args=["chat_id", "session_id", "ctype"])
    async def new(
        cls,
        db_conn: AsyncSession,
        *,
        chat_encryption_key: str,
        chat_id: str,
        session_id: str,
        ctype: str,
        content: str,
    ) -> None:
        """Insert a new context item in the database with encrypted content.

        Note: This always creates a new record. The context_key is unique per content,
        so identical content will be rejected by the database constraint.
        """
        now = datetime.now(UTC)

        if ctype not in VALID_CONTEXT_TYPES:
            raise InvalidContextTypeError(ctype)

        # Encrypt the content
        encrypted_content = cls.encrypt_content(
            content=json.dumps(content),
            chat_encryption_key=chat_encryption_key,
        )

        context_key = cls.generate_context_key(chat_id, ctype, encrypted_content)

        stmt = pg_insert(cls).values(
            context_key=context_key,
            chat_id=str(chat_id),
            session_id=session_id,
            type=ctype,
            encrypted_content=encrypted_content,
            created_at=now,
        )

        await db_conn.execute(stmt)

    @classmethod
    @traced(extract_args=["session_id"])
    async def get_by_session_id(
        cls,
        db_conn: AsyncSession,
        *,
        session_id: str,
        ctype: str | None = None,
    ) -> list["Context"] | None:
        """Retrieve a context by session_id, optionally filtered by type."""

        if ctype and ctype not in VALID_CONTEXT_TYPES:
            raise InvalidContextTypeError(ctype)

        stmt = select(cls).where(cls.session_id == session_id)

        if ctype:
            stmt = stmt.where(cls.type == ctype)

        result = await db_conn.execute(stmt)
        contexts = result.scalars().all()

        return contexts if contexts else None

    @classmethod
    @traced(extract_args=["chat_id"])
    async def get_by_chat_id(
        cls,
        db_conn: AsyncSession,
        *,
        chat_id: str,
        ctype: str | None = None,
    ) -> list["Context"] | None:
        """Retrieve a context by chat_id, optionally filtered by type."""

        if ctype and ctype not in VALID_CONTEXT_TYPES:
            raise InvalidContextTypeError(ctype)

        stmt = select(cls).where(cls.chat_id == chat_id)

        if ctype:
            stmt = stmt.where(cls.type == ctype)

        result = await db_conn.execute(stmt)
        contexts = result.scalars().all()

        return contexts if contexts else None

    @classmethod
    @traced(extract_args=["chat_id"])
    async def retrieve_context_by_chat(
        cls,
        db_conn: AsyncSession,
        *,
        chat_id: str,
        ctype: str | None = None,
    ) -> list["Context"] | None:
        """Retrieve contexts by chat_id and optional type, returning a list of Context objects."""

        if ctype and ctype not in VALID_CONTEXT_TYPES:
            raise InvalidContextTypeError(ctype)

        stmt = select(cls).where(cls.chat_id == chat_id)

        if ctype:
            stmt = stmt.where(cls.type == ctype)

        stmt = stmt.order_by(cls.created_at.desc())

        result = await db_conn.execute(stmt)
        contexts = result.scalars().all()

        return contexts if contexts else None

    @classmethod
    @traced(extract_args=["ids"])
    async def get_by_ids(
        cls,
        db_conn: AsyncSession,
        *,
        ids: list[int],
    ) -> list["Context"]:
        """Retrieve contexts by list of IDs.

        Args:
            db_conn: Database session
            ids: List of Context IDs to retrieve

        Returns:
            List of Context objects (may be empty if no matches)
        """
        if not ids:
            return []

        stmt = select(cls).where(cls.id.in_(ids))
        result = await db_conn.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    @traced(extract_args=["from_timestamp", "to_timestamp"])
    async def get_by_created_timestamp(
        cls,
        db_conn: AsyncSession,
        *,
        from_timestamp: datetime,
        to_timestamp: datetime,
    ) -> list["Context"]:
        """Retrieve contexts created after given timestamp.

        Args:
            db_conn: Database session
            from_timestamp: Datetime to query from (contexts created after this time)
            to_timestamp: Datetime to query to (contexts created before this time)

        Returns:
            List of Context objects ordered by created_at (oldest first)
        """
        stmt = (
            select(cls)
            .where(cls.created_at >= from_timestamp)
            .where(cls.created_at < to_timestamp)
            .order_by(cls.created_at.asc())
        )
        result = await db_conn.execute(stmt)
        return list(result.scalars().all())
