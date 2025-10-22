"""GuidedSession Pydantic model for guided interaction flows."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Literal

import pydantic
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import GuidedSessionsTable
from areyouok_telegram.data.models.messaging.chat import Chat
from areyouok_telegram.data.models.messaging.session import Session
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import db_retry


class GuidedSessionType(Enum):
    """Types of guided sessions supported by the system."""

    ONBOARDING = "onboarding"
    JOURNALING = "journaling"


class GuidedSessionState(Enum):
    """States for guided sessions - generic across all session types."""

    ACTIVE = "active"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class JournalContextMetadata(pydantic.BaseModel):
    phase: Literal["topic_selection", "journaling", "follow_up", "complete"]
    generated_topics: list[str]
    selected_topic: str | None = None


VALID_GUIDED_SESSION_STATES = [state.value for state in GuidedSessionState]
VALID_GUIDED_SESSION_TYPES = [session_type.value for session_type in GuidedSessionType]


class InvalidGuidedSessionStateError(Exception):
    def __init__(self, state: str):
        super().__init__(f"Invalid guided session state: {state}. Expected one of: {VALID_GUIDED_SESSION_STATES}.")
        self.state = state


class InvalidGuidedSessionTypeError(Exception):
    def __init__(self, session_type: str):
        super().__init__(f"Invalid guided session type: {session_type}. Expected one of: {VALID_GUIDED_SESSION_TYPES}.")
        self.session_type = session_type


class GuidedSession(pydantic.BaseModel):
    """Flexible guided session progress tracking for different session types."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Required fields
    chat: Chat
    session: Session
    session_type: str

    # Optional fields
    id: int = 0

    state: str = GuidedSessionState.INCOMPLETE.value
    started_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    metadata: dict = pydantic.Field(default_factory=dict)

    created_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))

    @property
    def object_key(self) -> str:
        """Generate a unique object key based on session ID, session type, and start time."""
        timestamp_str = self.started_at.isoformat()
        return hashlib.sha256(
            f"guided_session:{self.session_id}:{self.session_type}:{timestamp_str}".encode()
        ).hexdigest()

    @staticmethod
    def decrypt_metadata(encrypted_metadata: str, chat_encryption_key: str) -> dict:
        """Decrypt metadata using the chat's encryption key.

        Args:
            encrypted_metadata: The encrypted metadata string
            chat_encryption_key: The chat's Fernet encryption key

        Returns:
            Decrypted metadata dict

        Raises:
            ValueError: If the encryption key format is invalid
            InvalidToken: If the encryption key is wrong or data is corrupted
        """
        fernet = Fernet(chat_encryption_key.encode())
        encrypted_bytes = encrypted_metadata.encode("utf-8")
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        metadata_json = decrypted_bytes.decode("utf-8")
        return json.loads(metadata_json) if metadata_json else {}

    def encrypt_metadata(self) -> str:
        """Encrypt the metadata using the chat's encryption key.

        Returns:
            str: The encrypted metadata as base64-encoded string
        """
        chat_encryption_key = self.chat.retrieve_key()
        fernet = Fernet(chat_encryption_key.encode())
        metadata_str = json.dumps(self.metadata)
        encrypted_bytes = fernet.encrypt(metadata_str.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    @property
    def chat_id(self) -> int:
        """Get chat_id from the Chat object."""
        return self.chat.id

    @property
    def session_id(self) -> int:
        """Get session_id from the Session object."""
        return self.session.id

    @property
    def is_completed(self) -> bool:
        """Check if guided session is completed."""
        return self.state == GuidedSessionState.COMPLETE.value

    @property
    def is_active(self) -> bool:
        """Check if guided session is currently active."""
        return self.state == GuidedSessionState.ACTIVE.value

    @property
    def is_incomplete(self) -> bool:
        """Check if guided session is incomplete (timed out or abandoned)."""
        return self.state == GuidedSessionState.INCOMPLETE.value

    @property
    def is_expired(self) -> bool:
        """Check if active guided session has expired (older than 1 hour).

        Returns:
            True if session is ACTIVE and started more than 1 hour ago, False otherwise.
        """
        if not self.is_active:
            return False

        if not self.started_at:
            return False

        now = datetime.now(UTC)
        return now - self.started_at > timedelta(hours=1)

    @traced(extract_args=["chat_id", "session_id", "session_type"])
    @db_retry()
    async def save(self) -> GuidedSession:
        """Save or update the guided session in the database.

        Returns:
            GuidedSession instance refreshed from database
        """
        now = datetime.now(UTC)

        # Encrypt metadata for storage
        encrypted_metadata = None
        if self.metadata:
            encrypted_metadata = self.encrypt_metadata()

        async with async_database() as db_conn:
            values = {
                "object_key": self.object_key,
                "session_id": self.session.id,
                "chat_id": self.chat.id,
                "session_type": self.session_type,
                "state": self.state,
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "encrypted_metadata": encrypted_metadata,
                "created_at": self.created_at,
                "updated_at": now,
            }

            stmt = (
                pg_insert(GuidedSessionsTable)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["object_key"],
                    set_={
                        "state": values["state"],
                        "completed_at": values["completed_at"],
                        "encrypted_metadata": values["encrypted_metadata"],
                        "updated_at": values["updated_at"],
                    },
                )
                .returning(GuidedSessionsTable)
            )
            result = await db_conn.execute(stmt)
            row = result.scalar_one()

            # Return with decrypted metadata
            decrypted_metadata = {}
            if row.encrypted_metadata:
                chat_encryption_key = self.chat.retrieve_key()
                decrypted_metadata = self.decrypt_metadata(row.encrypted_metadata, chat_encryption_key)

            return GuidedSession(
                id=row.id,
                chat=self.chat,
                session=self.session,
                session_type=row.session_type,
                state=row.state,
                started_at=row.started_at,
                completed_at=row.completed_at,
                metadata=decrypted_metadata,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    @traced(extract_args=[])
    async def complete(self) -> GuidedSession:
        """Complete this guided session and save to database.

        Returns:
            Updated GuidedSession instance
        """
        self.state = GuidedSessionState.COMPLETE.value
        self.completed_at = datetime.now(UTC)
        return await self.save()

    @traced(extract_args=[])
    async def inactivate(self) -> GuidedSession:
        """Mark this guided session as inactive due to timeout and save to database.

        Returns:
            Updated GuidedSession instance
        """
        self.state = GuidedSessionState.INCOMPLETE.value
        return await self.save()

    @classmethod
    @traced(extract_args=["chat"])
    @db_retry()
    async def get_by_chat(
        cls,
        chat: Chat,
        *,
        session: Session | None = None,
        session_type: str | None = None,
        state: str | None = None,
    ) -> list[GuidedSession]:
        """Retrieve guided sessions for a chat with optional filtering.

        Args:
            chat: Chat object
            session: Optional Session to filter by
            session_type: Optional session type to filter by
            state: Optional state to filter by (active, complete, incomplete)

        Returns:
            List of GuidedSession instances ordered by created_at desc
        """
        async with async_database() as db_conn:
            stmt = select(GuidedSessionsTable).where(GuidedSessionsTable.chat_id == chat.id)

            if session:
                stmt = stmt.where(GuidedSessionsTable.session_id == session.id)

            if session_type:
                stmt = stmt.where(GuidedSessionsTable.session_type == session_type)

            if state:
                stmt = stmt.where(GuidedSessionsTable.state == state)

            stmt = stmt.order_by(GuidedSessionsTable.created_at.desc())
            result = await db_conn.execute(stmt)
            rows = result.scalars().all()

            # Convert to GuidedSession instances with loaded objects and decrypted metadata
            guided_sessions = []
            chat_encryption_key = chat.retrieve_key()

            for row in rows:
                # Load Session object
                session_obj = await Session.get_by_id(session_id=row.session_id)
                if not session_obj:
                    continue

                # Decrypt metadata
                decrypted_metadata = {}
                if row.encrypted_metadata and chat_encryption_key:
                    decrypted_metadata = cls.decrypt_metadata(row.encrypted_metadata, chat_encryption_key)

                guided_session = GuidedSession(
                    id=row.id,
                    chat=chat,
                    session=session_obj,
                    session_type=row.session_type,
                    state=row.state,
                    started_at=row.started_at,
                    completed_at=row.completed_at,
                    metadata=decrypted_metadata,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                guided_sessions.append(guided_session)

            return guided_sessions

    @classmethod
    @traced(extract_args=["guided_session_id"])
    @db_retry()
    async def get_by_id(
        cls,
        guided_session_id: int,
    ) -> GuidedSession | None:
        """Retrieve a guided session by ID with loaded objects and decrypted metadata.

        Args:
            guided_session_id: Internal guided session ID

        Returns:
            GuidedSession instance if found, None otherwise
        """
        async with async_database() as db_conn:
            stmt = select(GuidedSessionsTable).where(GuidedSessionsTable.id == guided_session_id)
            result = await db_conn.execute(stmt)
            row = result.scalars().first()

            if row is None:
                return None

            # Load Chat and Session objects
            chat = await Chat.get_by_id(chat_id=row.chat_id)
            session = await Session.get_by_id(session_id=row.session_id)

            if not chat or not session:
                return None

            # Decrypt metadata
            decrypted_metadata = {}
            if row.encrypted_metadata:
                chat_encryption_key = chat.retrieve_key()
                if chat_encryption_key:
                    decrypted_metadata = cls.decrypt_metadata(row.encrypted_metadata, chat_encryption_key)

            return GuidedSession(
                id=row.id,
                chat=chat,
                session=session,
                session_type=row.session_type,
                state=row.state,
                started_at=row.started_at,
                completed_at=row.completed_at,
                metadata=decrypted_metadata,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
