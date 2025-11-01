"""Context Pydantic model for session context and metadata."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import pydantic
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import ContextTable
from areyouok_telegram.data.models.messaging.chat import Chat
from areyouok_telegram.data.models.messaging.session import Session
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import db_retry


class ContextType(Enum):
    SESSION = "session"
    RESPONSE = "response"
    PERSONALITY = "personality"
    METADATA = "metadata"
    ACTION = "action"
    MEMORY = "memory"
    PROFILE = "profile"
    PROFILE_UPDATE = "profile_update"


VALID_CONTEXT_TYPES = [context_type.value for context_type in ContextType]


class InvalidContextTypeError(Exception):
    def __init__(self, context_type: str):
        super().__init__(f"Invalid context type: {context_type}. Expected one of: {VALID_CONTEXT_TYPES}.")
        self.context_type = context_type


class Context(pydantic.BaseModel):
    """Session context and metadata model."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Required fields
    chat: Chat
    type: str
    content: Any

    # Optional fields
    id: int = 0
    session_id: int | None = None
    created_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))

    @property
    def chat_id(self) -> int:
        """Get chat_id from the Chat object."""
        return self.chat.id

    @property
    def object_key(self) -> str:
        content_b64 = base64.b64encode(json.dumps(self.content).encode()).decode()
        timestamp_str = self.created_at.isoformat()
        return hashlib.sha256(f"context:{self.chat.id}:{self.type}:{content_b64}:{timestamp_str}".encode()).hexdigest()

    @staticmethod
    def decrypt_content(encrypted_content: str, chat_encryption_key: str) -> Any:
        """Decrypt the content using the chat's encryption key.

        Args:
            encrypted_content: The encrypted content string
            chat_encryption_key: The chat's Fernet encryption key

        Returns:
            Decrypted content as python object
        """
        fernet = Fernet(chat_encryption_key.encode())
        encrypted_bytes = encrypted_content.encode("utf-8")
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        content_json = decrypted_bytes.decode("utf-8")
        return json.loads(content_json)

    def encrypt_content(self) -> str:
        """Encrypt the content using the chat's encryption key.

        Args:
            content: The content to encrypt
            chat_encryption_key: The chat's Fernet encryption key

        Returns:
            str: The encrypted content as base64-encoded string
        """
        fernet = Fernet(self.chat.retrieve_key().encode())
        content_json = json.dumps(self.content)
        encrypted_bytes = fernet.encrypt(content_json.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    @traced(extract_args=False)
    @db_retry()
    async def save(self) -> Context:
        """Save the context to the database with encrypted content.

        Note: This always creates a new record. The object_key includes timestamp,
        so identical content can be saved at different times.

        Returns:
            Context instance refreshed from database (with decrypted content)
        """
        # Encrypt the content for storage
        encrypted_content = self.encrypt_content()

        async with async_database() as db_conn:
            stmt = (
                pg_insert(ContextTable)
                .values(
                    object_key=self.object_key,
                    chat_id=self.chat.id,
                    session_id=self.session_id,
                    type=self.type,
                    encrypted_content=encrypted_content,
                    created_at=self.created_at,
                )
                .returning(ContextTable)
            )

            result = await db_conn.execute(stmt)
            row = result.scalar_one()

            # Return Context with the chat object and decrypted content
            return Context(
                id=row.id,
                chat=self.chat,
                session_id=row.session_id,
                type=row.type,
                content=self.content,
                created_at=row.created_at,
            )

    @classmethod
    @db_retry()
    async def get_by_chat(
        cls,
        chat: Chat,
        *,
        session: Session | None = None,
        ctype: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> list[Context]:
        """Retrieve contexts for a chat with optional filtering, auto-decrypted.

        Args:
            chat: Chat object (provides chat_id and encryption key)
            session: Optional Session to filter by
            ctype: Optional context type to filter by
            from_timestamp: Optional start of time range (inclusive)
            to_timestamp: Optional end of time range (exclusive)

        Returns:
            List of decrypted Context instances (empty list if no matches)

        Raises:
            InvalidContextTypeError: If context type is invalid
        """
        if ctype and ctype not in VALID_CONTEXT_TYPES:
            raise InvalidContextTypeError(ctype)

        async with async_database() as db_conn:
            stmt = select(ContextTable).where(ContextTable.chat_id == chat.id)

            # Apply optional filters
            if session:
                stmt = stmt.where(ContextTable.session_id == session.id)

            if ctype:
                stmt = stmt.where(ContextTable.type == ctype)

            if from_timestamp:
                stmt = stmt.where(ContextTable.created_at >= from_timestamp)

            if to_timestamp:
                stmt = stmt.where(ContextTable.created_at < to_timestamp)

            stmt = stmt.order_by(ContextTable.created_at.desc())

            result = await db_conn.execute(stmt)
            rows = result.scalars().all()

            # Convert to Context instances and decrypt content
            encryption_key = chat.retrieve_key()
            contexts = []
            for row in rows:
                # Decrypt content during construction
                decrypted_content = None
                if encryption_key:
                    decrypted_content = cls.decrypt_content(row.encrypted_content, encryption_key)

                context = Context(
                    id=row.id,
                    chat=chat,
                    session_id=row.session_id,
                    type=row.type,
                    content=decrypted_content,
                    created_at=row.created_at,
                )
                contexts.append(context)

            return contexts

    @classmethod
    @traced(extract_args=["context_id"])
    @db_retry()
    async def get_by_id(
        cls,
        chat: Chat,
        *,
        context_id: int,
    ) -> Context | None:
        """Retrieve a single context by ID, auto-decrypted.

        Args:
            chat: Chat object (provides encryption key)
            context_id: Internal context ID

        Returns:
            Decrypted Context instance if found, None otherwise
        """
        async with async_database() as db_conn:
            stmt = select(ContextTable).where(ContextTable.id == context_id)
            result = await db_conn.execute(stmt)
            row = result.scalars().first()

            if row is None:
                return None

            # Auto-decrypt content
            encryption_key = chat.retrieve_key()
            decrypted_content = None
            if encryption_key:
                decrypted_content = cls.decrypt_content(row.encrypted_content, encryption_key)

            return Context(
                id=row.id,
                chat=chat,
                session_id=row.session_id,
                type=row.type,
                content=decrypted_content,
                created_at=row.created_at,
            )
