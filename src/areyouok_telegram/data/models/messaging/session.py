"""Session Pydantic model for conversation sessions."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pydantic
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import SessionsTable
from areyouok_telegram.data.models.messaging.chat import Chat
from areyouok_telegram.logging import traced


class Session(pydantic.BaseModel):
    """Conversation session model."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Required fields
    chat: Chat
    session_start: datetime

    # Optional fields
    id: int = 0
    session_end: datetime | None = None
    last_user_message: datetime | None = None
    last_user_activity: datetime | None = None
    last_bot_message: datetime | None = None
    last_bot_activity: datetime | None = None
    message_count: int = 0

    @property
    def object_key(self) -> str:
        """Generate a unique object key for a session based on chat ID and start time."""
        timestamp_str = self.session_start.isoformat()
        return hashlib.sha256(f"session:{self.chat.id}:{timestamp_str}".encode()).hexdigest()

    @property
    def chat_id(self) -> int:
        """Get chat_id from the Chat object."""
        return self.chat.id

    @property
    def has_bot_responded(self) -> bool:
        """Check if the bot has responded to the latest updates in the session."""
        if not self.last_user_activity:
            return True

        if not self.last_bot_activity:
            return False

        return self.last_bot_activity > self.last_user_activity

    @traced(extract_args=["chat_id"])
    async def save(self) -> Session:
        """Save or update the session in the database.

        Returns:
            Session instance refreshed from database
        """
        async with async_database() as db_conn:
            stmt = (
                pg_insert(SessionsTable)
                .values(
                    object_key=self.object_key,
                    chat_id=self.chat.id,
                    session_start=self.session_start,
                    session_end=self.session_end,
                    last_user_message=self.last_user_message,
                    last_user_activity=self.last_user_activity,
                    last_bot_message=self.last_bot_message,
                    last_bot_activity=self.last_bot_activity,
                    message_count=self.message_count,
                )
                .on_conflict_do_update(
                    index_elements=["object_key"],
                    set_={
                        "session_end": self.session_end,
                        "last_user_message": self.last_user_message,
                        "last_user_activity": self.last_user_activity,
                        "last_bot_message": self.last_bot_message,
                        "last_bot_activity": self.last_bot_activity,
                        "message_count": self.message_count,
                    },
                )
                .returning(SessionsTable)
            )

            result = await db_conn.execute(stmt)
            row = result.scalar_one()

            # Return with Chat object
            return Session(
                id=row.id,
                chat=self.chat,
                session_start=row.session_start,
                session_end=row.session_end,
                last_user_message=row.last_user_message,
                last_user_activity=row.last_user_activity,
                last_bot_message=row.last_bot_message,
                last_bot_activity=row.last_bot_activity,
                message_count=row.message_count,
            )

    @traced(extract_args=["timestamp", "is_user"])
    async def new_activity(self, *, timestamp: datetime, is_user: bool) -> Session:
        """Record user activity (like edits) without incrementing message count.

        Args:
            timestamp: Activity timestamp
            is_user: True if user activity, False if bot activity

        Returns:
            Updated Session instance
        """
        if is_user:
            self.last_user_activity = max(self.last_user_activity, timestamp) if self.last_user_activity else timestamp
        else:
            self.last_bot_activity = max(self.last_bot_activity, timestamp) if self.last_bot_activity else timestamp

        return await self.save()

    @traced(extract_args=["timestamp", "is_user"])
    async def new_message(self, *, timestamp: datetime, is_user: bool) -> Session:
        """Record a new message in the session, updating appropriate timestamps and saving.

        Args:
            timestamp: Message timestamp
            is_user: True if user message, False if bot message

        Returns:
            Updated Session instance
        """
        if is_user:
            self.last_user_activity = max(self.last_user_activity, timestamp) if self.last_user_activity else timestamp
            self.last_user_message = max(self.last_user_message, timestamp) if self.last_user_message else timestamp
            # Increment message count only for user messages
            self.message_count = self.message_count + 1 if self.message_count is not None else 1
        else:
            self.last_bot_activity = max(self.last_bot_activity, timestamp) if self.last_bot_activity else timestamp
            self.last_bot_message = max(self.last_bot_message, timestamp) if self.last_bot_message else timestamp

        return await self.save()

    @traced(extract_args=["timestamp"])
    async def close_session(self, *, timestamp: datetime) -> Session:
        """Close a session by setting session_end and saving.

        Args:
            timestamp: Session end timestamp

        Returns:
            Updated Session instance
        """
        self.session_end = timestamp
        return await self.save()

    @classmethod
    async def get_or_create_new_session(cls, *, chat: Chat, session_start: datetime | None = None) -> Session:
        """Get or create a new session for a chat.
        Args:
            chat: Chat object
        Returns:
            Session instance
        """

        session = await cls.get_sessions(chat=chat, active=True)
        if session:
            return session
        else:
            session_start = session_start or datetime.now(UTC)
            new_session = cls(chat=chat, session_start=session_start)
            return await new_session.save()

    @classmethod
    @traced(extract_args=["chat", "active"])
    async def get_sessions(
        cls,
        *,
        chat: Chat | None = None,
        active: bool | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> list[Session]:
        """Retrieve sessions with flexible filtering.

        Args:
            chat: Optional Chat object to filter by
            active: None (all), True (active only), False (inactive only)
            from_timestamp: Optional start of time range (for inactive sessions)
            to_timestamp: Optional end of time range (for inactive sessions)

        Returns:
            List of Session instances with Chat objects loaded
        """
        async with async_database() as db_conn:
            stmt = select(SessionsTable)

            # Filter by chat if provided
            if chat:
                stmt = stmt.where(SessionsTable.chat_id == chat.id)

            # Filter by active status
            if active is True:
                stmt = stmt.where(SessionsTable.session_end.is_(None))
            elif active is False:
                stmt = stmt.where(SessionsTable.session_end.is_not(None))

            # Filter by time range (typically for inactive sessions)
            if from_timestamp:
                stmt = stmt.where(SessionsTable.session_end >= from_timestamp)
            if to_timestamp:
                stmt = stmt.where(SessionsTable.session_end < to_timestamp)

            stmt = stmt.order_by(SessionsTable.session_start.desc())

            result = await db_conn.execute(stmt)
            rows = result.scalars().all()

            # Load Chat objects for each session
            sessions = []
            for row in rows:
                # Use provided chat or load it
                if chat and row.chat_id == chat.id:
                    session_chat = chat
                else:
                    session_chat = await Chat.get_by_id(chat_id=row.chat_id)
                    if not session_chat:
                        continue

                session = Session(
                    id=row.id,
                    chat=session_chat,
                    session_start=row.session_start,
                    session_end=row.session_end,
                    last_user_message=row.last_user_message,
                    last_user_activity=row.last_user_activity,
                    last_bot_message=row.last_bot_message,
                    last_bot_activity=row.last_bot_activity,
                    message_count=row.message_count,
                )
                sessions.append(session)

            return sessions

    @classmethod
    async def get_by_id(cls, *, session_id: int) -> Session | None:
        """Retrieve a session by its internal ID.

        Args:
            session_id: Internal session ID

        Returns:
            Session instance if found, None otherwise
        """
        async with async_database() as db_conn:
            stmt = select(SessionsTable).where(SessionsTable.id == session_id)
            result = await db_conn.execute(stmt)
            row = result.scalars().first()

            if row is None:
                return None

            # Load Chat object
            chat = await Chat.get_by_id(chat_id=row.chat_id)
            if not chat:
                return None

            return Session(
                id=row.id,
                chat=chat,
                session_start=row.session_start,
                session_end=row.session_end,
                last_user_message=row.last_user_message,
                last_user_activity=row.last_user_activity,
                last_bot_message=row.last_bot_message,
                last_bot_activity=row.last_bot_activity,
                message_count=row.message_count,
            )
