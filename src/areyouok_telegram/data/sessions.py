import hashlib
from datetime import UTC
from datetime import datetime
from typing import Literal
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


class InvalidMessageTypeError(ValueError):
    """Raised when an invalid message type is provided."""

    def __init__(self, message_type: str) -> None:
        super().__init__(f"Invalid message_type: {message_type}. Must be 'user' or 'bot'.")


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

    message_count = Column(Integer, nullable=True)

    id = Column(Integer, primary_key=True, autoincrement=True)

    @property
    def has_bot_responded(self) -> bool:
        """Check if the bot has responded to the latest updates in the session."""
        if not self.last_bot_message:
            return False

        if not self.last_user_message:
            return True

        return self.last_bot_message > self.last_user_message

    @staticmethod
    def generate_session_key(chat_id: str, session_start: datetime) -> str:
        """Generate a unique key for a session based on chat ID and start time."""
        timestamp_str = session_start.isoformat()
        return hashlib.sha256(f"{chat_id}:{timestamp_str}".encode()).hexdigest()

    @classmethod
    @with_retry()
    async def get_active_session(cls, session: AsyncSession, chat_id: str) -> Optional["Sessions"]:
        """Get the active (non-closed) session for a chat."""
        stmt = select(cls).where(cls.chat_id == chat_id).where(cls.session_end.is_(None))

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    @with_retry()
    async def get_inactive_sessions(cls, session: AsyncSession, cutoff_time: datetime) -> list["Sessions"]:
        """Get all sessions that have been inactive since cutoff_time."""
        stmt = (
            select(cls)
            .where(cls.session_end.is_(None))  # Only active sessions
            .where(
                (cls.last_user_activity.is_not(None)) & (cls.last_user_activity < cutoff_time)
            )  # Inactive for more than cutoff (only if activity exists)
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

    @with_retry()
    async def new_message(self, timestamp: datetime, message_type: Literal["user", "bot"]) -> None:
        """Record a new message in the session, updating appropriate timestamps."""
        # Always update user activity timestamp
        self.last_user_activity = max(self.last_user_activity, timestamp) if self.last_user_activity else timestamp

        if message_type == "user":
            self.last_user_message = max(self.last_user_message, timestamp) if self.last_user_message else timestamp
            # Increment message count only for user messages
            self.message_count = self.message_count + 1 if self.message_count is not None else 1
        elif message_type == "bot":
            self.last_bot_message = max(self.last_bot_message, timestamp) if self.last_bot_message else timestamp
        else:
            raise InvalidMessageTypeError(message_type)

    @with_retry()
    async def new_user_activity(self, timestamp: datetime) -> None:
        """Record user activity (like edits) without incrementing message count."""
        self.last_user_activity = timestamp

    @with_retry()
    async def close_session(self, session: AsyncSession) -> None:
        """Close a session by setting session_end and message_count."""
        messages = await self.get_messages(session)
        self.session_end = datetime.now(UTC)
        self.message_count = len(messages)

    @with_retry()
    async def get_messages(self, session: AsyncSession) -> list[telegram.Message]:
        """Retrieve all messages from this session."""
        # Determine the end time - either session_end or current time for active sessions
        end_time = self.session_end if self.session_end else datetime.now(UTC)

        return await Messages.retrieve_by_chat(
            session=session, chat_id=self.chat_id, from_time=self.session_start, to_time=end_time
        )
