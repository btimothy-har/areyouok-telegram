import hashlib
from datetime import UTC
from datetime import datetime
from typing import Optional

import telegram
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data.connection import Base
from areyouok_telegram.data.messages import Messages
from areyouok_telegram.data.utils import with_retry


class Sessions(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": ENV}

    session_key = Column(String, nullable=False, unique=True)
    chat_id = Column(String, nullable=False)
    session_start = Column(TIMESTAMP(timezone=True), nullable=False)
    session_end = Column(TIMESTAMP(timezone=True), nullable=True)
    last_user_message = Column(TIMESTAMP(timezone=True), nullable=True)
    last_user_activity = Column(TIMESTAMP(timezone=True), nullable=True)
    last_bot_message = Column(TIMESTAMP(timezone=True), nullable=True)
    last_bot_activity = Column(TIMESTAMP(timezone=True), nullable=True)

    message_count = Column(Integer, nullable=True)

    id = Column(Integer, primary_key=True, autoincrement=True)

    @property
    def has_bot_responded(self) -> bool:
        """Check if the bot has responded to the latest updates in the session."""
        if not self.last_bot_activity:
            return False

        if not self.last_user_activity:
            return True

        return self.last_bot_activity > self.last_user_activity

    @staticmethod
    def generate_session_key(chat_id: str, session_start: datetime) -> str:
        """Generate a unique key for a session based on chat ID and start time."""
        timestamp_str = session_start.isoformat()
        return hashlib.sha256(f"{chat_id}:{timestamp_str}".encode()).hexdigest()

    @with_retry()
    async def new_message(self, timestamp: datetime, *, is_user: bool) -> None:
        """Record a new message in the session, updating appropriate timestamps."""
        # Always update new activity timestamp
        await self.new_activity(timestamp, is_user=is_user)

        if is_user:
            self.last_user_message = max(self.last_user_message, timestamp) if self.last_user_message else timestamp
            # Increment message count only for user messages
            self.message_count = self.message_count + 1 if self.message_count is not None else 1

        else:
            self.last_bot_message = max(self.last_bot_message, timestamp) if self.last_bot_message else timestamp

    @with_retry()
    async def new_activity(self, timestamp: datetime, *, is_user: bool) -> None:
        """Record user activity (like edits) without incrementing message count."""
        if is_user:
            self.last_user_activity = max(self.last_user_activity, timestamp) if self.last_user_activity else timestamp

        else:
            self.last_bot_activity = max(self.last_bot_activity, timestamp) if self.last_bot_activity else timestamp

    @with_retry()
    async def close_session(self, session: AsyncSession, timestamp: datetime) -> None:
        """Close a session by setting session_end and message_count."""
        messages = await self.get_messages(session)
        self.session_end = timestamp
        self.message_count = len(messages)

    @with_retry()
    async def get_messages(self, session: AsyncSession) -> list[telegram.Message]:
        """Retrieve all messages from this session."""
        # Determine the end time - either session_end or current time for active sessions
        end_time = self.session_end if self.session_end else datetime.now(UTC)

        return await Messages.retrieve_by_chat(
            session=session, chat_id=self.chat_id, from_time=self.session_start, to_time=end_time
        )

    @classmethod
    @with_retry()
    async def get_active_session(cls, session: AsyncSession, chat_id: str) -> Optional["Sessions"]:
        """Get the active (non-closed) session for a chat."""
        stmt = select(cls).where(cls.chat_id == chat_id).where(cls.session_end.is_(None))

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    @with_retry()
    async def get_all_active_sessions(cls, session: AsyncSession) -> list["Sessions"]:
        """Get all active (non-closed) sessions."""
        stmt = select(cls).where(cls.session_end.is_(None))  # Only active sessions

        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    @with_retry()
    async def get_all_inactive_sessions(
        cls, session: AsyncSession, from_dt: datetime, to_dt: datetime
    ) -> list["Sessions"]:
        """Get all inactive (closed) sessions that ended within the given time range.

        Args:
            session: The database session to use for the query.
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

        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    @with_retry()
    async def create_session(cls, session: AsyncSession, chat_id: str, timestamp: datetime) -> "Sessions":
        """Create a new session for a chat."""
        session_key = cls.generate_session_key(chat_id, timestamp)

        new_session = cls(
            session_key=session_key,
            chat_id=chat_id,
            session_start=timestamp,
        )

        session.add(new_session)
        return new_session
