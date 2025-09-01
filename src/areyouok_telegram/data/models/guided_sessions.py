import hashlib
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from enum import Enum

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
from areyouok_telegram.utils import traced


class GuidedSessionType(Enum):
    """Types of guided sessions supported by the system."""

    ONBOARDING = "onboarding"
    # Future session types can be added here:
    # MINDFULNESS = "mindfulness"
    # GOAL_SETTING = "goal_setting"


class GuidedSessionState(Enum):
    """States for guided sessions - generic across all session types."""

    ACTIVE = "active"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


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


class GuidedSessions(Base):
    """Flexible guided session progress tracking for different session types."""

    __tablename__ = "guided_sessions"
    __table_args__ = {"schema": ENV}

    guided_session_key = Column(String, nullable=False, unique=True)
    chat_session = Column(
        String,
        ForeignKey(f"{ENV}.sessions.session_key"),
        nullable=False,
        index=True,
    )
    chat_id = Column(String, nullable=False)
    session_type = Column(String, nullable=False, index=True)

    # Session State Management
    state = Column(String, nullable=False, default=GuidedSessionState.INCOMPLETE.value)
    started_at = Column(TIMESTAMP(timezone=True), nullable=False)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Metadata
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_guided_session_key(chat_session: str, session_type: str, started_at: datetime) -> str:
        """Generate a unique guided session key based on chat session, session type, and start time."""
        timestamp_str = started_at.isoformat()
        return hashlib.sha256(f"{session_type}:{chat_session}:{timestamp_str}".encode()).hexdigest()

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

    @classmethod
    @traced(extract_args=["chat_session", "session_type"])
    async def start_new_session(
        cls, db_conn: AsyncSession, *, chat_id: str, chat_session: str, session_type: str
    ) -> "GuidedSessions":
        """Start a guided session for a user.

        Creates a new guided session record, preserving audit trail of previous attempts.

        Args:
            db_conn: Database connection
            user_id: User ID to start guided session for
            chat_session: Session key from Sessions table to link to
            session_type: Type of guided session (from GuidedSessionType enum)

        Returns:
            GuidedSessions: Active guided session state object

        Raises:
            InvalidGuidedSessionTypeError: If session_type is not valid
        """
        # Validate session type
        if session_type not in VALID_GUIDED_SESSION_TYPES:
            raise InvalidGuidedSessionTypeError(session_type)

        now = datetime.now(UTC)
        guided_session_key = cls.generate_guided_session_key(chat_session, session_type, now)

        values = {
            "guided_session_key": guided_session_key,
            "chat_session": chat_session,
            "chat_id": chat_id,
            "session_type": session_type,
            "state": GuidedSessionState.ACTIVE.value,
            "started_at": now,
            "created_at": now,
            "updated_at": now,
        }

        stmt = pg_insert(cls).values(**values)
        await db_conn.execute(stmt)

    @traced(extract_args=["timestamp"])
    async def complete(self, db_conn: AsyncSession, *, timestamp: datetime) -> None:
        """Complete this guided session.

        Args:
            db_conn: Database connection
            timestamp: Completion timestamp
        """
        self.state = GuidedSessionState.COMPLETE.value
        self.completed_at = timestamp
        self.updated_at = timestamp
        db_conn.add(self)

    @traced(extract_args=["timestamp"])
    async def inactivate(self, db_conn: AsyncSession, *, timestamp: datetime) -> None:
        """Mark this guided session as inactive due to timeout.

        Args:
            db_conn: Database connection
            timestamp: Inactivation timestamp
        """
        self.state = GuidedSessionState.INCOMPLETE.value
        self.updated_at = timestamp
        db_conn.add(self)

    @classmethod
    async def get_by_chat_id(
        cls,
        db_conn: AsyncSession,
        *,
        chat_id: str,
        session_type: str | None = None,
    ) -> list["GuidedSessions"]:
        """Retrieve all guided sessions by chat ID, optionally filtered by session type."""
        stmt = select(cls).where(cls.chat_id == chat_id)

        if session_type:
            stmt = stmt.where(cls.session_type == session_type)

        stmt = stmt.order_by(cls.created_at.desc())
        result = await db_conn.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_by_chat_session(
        cls,
        db_conn: AsyncSession,
        *,
        chat_session: str,
        session_type: str | None = None,
    ) -> list["GuidedSessions"]:
        """Retrieve all guided sessions by chat session, optionally filtered by session type."""
        stmt = select(cls).where(cls.chat_session == chat_session)

        if session_type:
            stmt = stmt.where(cls.session_type == session_type)

        stmt = stmt.order_by(cls.created_at.desc())
        result = await db_conn.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_by_guided_session_key(
        cls,
        db_conn: AsyncSession,
        *,
        guided_session_key: str,
    ) -> "GuidedSessions" | None:
        """Retrieve guided session by its unique guided_session_key."""
        stmt = select(cls).where(cls.guided_session_key == guided_session_key)
        result = await db_conn.execute(stmt)
        return result.scalars().one_or_none()
