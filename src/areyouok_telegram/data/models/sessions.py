import hashlib
from datetime import datetime
from typing import Optional

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.data import Messages
from areyouok_telegram.utils import traced


class Sessions(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": ENV}

    session_key = Column(String, nullable=False, unique=True)
    chat_id = Column(String, nullable=False)

    # Onboarding relationship
    onboarding_key = Column(
        String,
        ForeignKey(f"{ENV}.onboarding.session_key"),
        nullable=True,
    )

    session_start = Column(TIMESTAMP(timezone=True), nullable=False)
    session_end = Column(TIMESTAMP(timezone=True), nullable=True)

    last_user_message = Column(TIMESTAMP(timezone=True), nullable=True)
    last_user_activity = Column(TIMESTAMP(timezone=True), nullable=True)
    last_bot_message = Column(TIMESTAMP(timezone=True), nullable=True)
    last_bot_activity = Column(TIMESTAMP(timezone=True), nullable=True)

    message_count = Column(Integer, nullable=True)

    id = Column(Integer, primary_key=True, autoincrement=True)

    @staticmethod
    def generate_session_key(chat_id: str, session_start: datetime) -> str:
        """Generate a unique key for a session based on chat ID and start time."""
        timestamp_str = session_start.isoformat()
        return hashlib.sha256(f"{chat_id}:{timestamp_str}".encode()).hexdigest()

    @property
    def session_id(self) -> str:
        """Return the unique session ID, which is the session key."""
        return self.session_key

    @property
    def is_onboarding(self) -> bool:
        """Check if this session is for onboarding."""
        return self.onboarding_key is not None

    @property
    def has_bot_responded(self) -> bool:
        """Check if the bot has responded to the latest updates in the session."""
        if not self.last_user_activity:
            return True

        if not self.last_bot_activity:
            return False

        return self.last_bot_activity > self.last_user_activity

    @traced(extract_args=["timestamp", "is_user"])
    async def new_message(self, db_conn: AsyncSession, *, timestamp: datetime, is_user: bool) -> None:
        """Record a new message in the session, updating appropriate timestamps."""
        # Always update new activity timestamp
        await self.new_activity(db_conn, timestamp=timestamp, is_user=is_user)

        if is_user:
            self.last_user_message = max(self.last_user_message, timestamp) if self.last_user_message else timestamp
            # Increment message count only for user messages
            self.message_count = self.message_count + 1 if self.message_count is not None else 1

        else:
            self.last_bot_message = max(self.last_bot_message, timestamp) if self.last_bot_message else timestamp

        db_conn.add(self)

    @traced(extract_args=["timestamp", "is_user"])
    async def new_activity(self, db_conn: AsyncSession, *, timestamp: datetime, is_user: bool) -> None:
        """Record user activity (like edits) without incrementing message count."""
        if is_user:
            self.last_user_activity = max(self.last_user_activity, timestamp) if self.last_user_activity else timestamp

        else:
            self.last_bot_activity = max(self.last_bot_activity, timestamp) if self.last_bot_activity else timestamp

        db_conn.add(self)

    @traced(extract_args=["timestamp"])
    async def close_session(self, db_conn: AsyncSession, *, timestamp: datetime) -> None:
        """Close a session by setting session_end and message_count."""
        messages = await self.get_messages(db_conn)
        self.session_end = timestamp
        self.message_count = len(messages)

        db_conn.add(self)

    @traced(extract_args=["onboarding_key"])
    async def attach_onboarding(self, db_conn: AsyncSession, *, onboarding_key: str) -> None:
        """Attach an onboarding session to this chat session."""
        self.onboarding_key = onboarding_key
        db_conn.add(self)

    @traced(extract_args=False)
    async def get_messages(self, db_conn: AsyncSession) -> list["Messages"]:
        """Retrieve all raw messages from this session."""

        return await Messages.retrieve_by_session(db_conn, session_id=self.session_id)

    @classmethod
    @traced(extract_args=["chat_id", "timestamp", "is_onboarding"], record_return=True)
    async def create_session(
        cls,
        db_conn: AsyncSession,
        *,
        chat_id: str,
        timestamp: datetime,
    ) -> "Sessions":
        """Create a new session for a chat.
        If a session already exists, it will return the currently active session.

        Args:
            db_conn: The database connection to use for the query.
            chat_id: The unique identifier for the chat.
            timestamp: The start time of the session.
            onboarding_key: Link to the OnboardingSession session key.
        Returns:
            The active session object, either newly created or existing.
        """
        session_key = cls.generate_session_key(chat_id, timestamp)

        stmt = pg_insert(cls).values(
            session_key=session_key,
            chat_id=chat_id,
            session_start=timestamp,
        )

        # On conflict, update the session_start to ensure we always return something
        # This handles race conditions where the same session might be created twice
        stmt = stmt.on_conflict_do_update(
            index_elements=["session_key"],
            set_={"session_start": timestamp},  # Update timestamp to latest attempt
        ).returning(cls)

        result = await db_conn.execute(stmt)
        return result.scalar_one()  # Always returns the active session object

    @classmethod
    async def get_active_session(cls, db_conn: AsyncSession, *, chat_id: str) -> Optional["Sessions"]:
        """Get the active (non-closed) session for a chat."""
        stmt = select(cls).where(cls.chat_id == chat_id).where(cls.session_end.is_(None))

        result = await db_conn.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_onboarding_key(cls, db_conn: AsyncSession, *, onboarding_key: str) -> list["Sessions"]:
        """Get all sessions related to an onboarding session.

        Args:
            db_conn: Database connection
            onboarding_key: The onboarding session key to search for

        Returns:
            List of Sessions objects linked to this onboarding
        """
        stmt = select(cls).where(cls.onboarding_key == onboarding_key)
        result = await db_conn.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    @traced(extract_args=False)
    async def get_all_active_sessions(cls, db_conn: AsyncSession) -> list["Sessions"]:
        """Get all active (non-closed) sessions."""
        stmt = select(cls).where(cls.session_end.is_(None))  # Only active sessions

        result = await db_conn.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    @traced(extract_args=["from_dt", "to_dt"])
    async def get_all_inactive_sessions(
        cls, db_conn: AsyncSession, from_dt: datetime, to_dt: datetime
    ) -> list["Sessions"]:
        """Get all inactive (closed) sessions that ended within the given time range.

        Args:
            db_conn: The database connection to use for the query.
            from_dt: The start of the time range (inclusive).
            to_dt: The end of the time range (exclusive).

        Returns:
            A list of Sessions that ended >= from_dt and < to_dt.
        """
        stmt = (
            select(cls)
            .where(cls.session_end.is_not(None))
            .where(cls.session_end >= from_dt)
            .where(cls.session_end < to_dt)
        )

        result = await db_conn.execute(stmt)
        return list(result.scalars().all())
