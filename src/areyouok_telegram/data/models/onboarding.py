import hashlib
from datetime import UTC
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.utils import traced


class OnboardingState(Enum):
    """Simplified onboarding states."""

    ACTIVE = "active"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


VALID_ONBOARDING_STATES = [state.value for state in OnboardingState]


class InvalidOnboardingStateError(Exception):
    def __init__(self, state: str):
        super().__init__(f"Invalid onboarding state: {state}. Expected one of: {VALID_ONBOARDING_STATES}.")
        self.state = state


class OnboardingSession(Base):
    """User onboarding progress tracking."""

    __tablename__ = "onboarding"
    __table_args__ = {"schema": ENV}

    session_key = Column(String, nullable=False, unique=True)
    user_id = Column(String, nullable=False)

    # Onboarding State Management
    state = Column(String, nullable=False, default=OnboardingState.INCOMPLETE.value)
    started_at = Column(TIMESTAMP(timezone=True), nullable=False)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Metadata
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_session_key(user_id: str, started_at: datetime) -> str:
        """Generate a unique session key for onboarding based on user ID and start time."""
        timestamp_str = started_at.isoformat()
        return hashlib.sha256(f"onboarding:{user_id}:{timestamp_str}".encode()).hexdigest()

    @property
    def is_completed(self) -> bool:
        """Check if onboarding is completed."""
        return self.state == OnboardingState.COMPLETE.value

    @property
    def is_active(self) -> bool:
        """Check if onboarding is currently active."""
        return self.state == OnboardingState.ACTIVE.value

    @property
    def is_incomplete(self) -> bool:
        """Check if onboarding is incomplete (timed out or abandoned)."""
        return self.state == OnboardingState.INCOMPLETE.value

    @classmethod
    @traced(extract_args=["user_id"])
    async def start_onboarding(cls, db_conn: AsyncSession, *, user_id: str) -> "OnboardingSession":
        """Start onboarding for a user.

        Creates a new onboarding record, preserving audit trail of previous attempts.

        Args:
            db_conn: Database connection
            user_id: User ID to start onboarding for

        Returns:
            OnboardingSession: Active onboarding state object
        """
        now = datetime.now(UTC)
        session_key = cls.generate_session_key(user_id, now)

        values = {
            "session_key": session_key,
            "user_id": user_id,
            "state": OnboardingState.ACTIVE.value,
            "started_at": now,
            "created_at": now,
            "updated_at": now,
        }

        stmt = pg_insert(cls).values(**values)
        await db_conn.execute(stmt)

        # Return the most recent onboarding state for this user
        return await cls.get_by_user_id(db_conn, user_id=user_id)

    @traced(extract_args=[])
    async def end_onboarding(self, db_conn: AsyncSession, *, timestamp: datetime) -> None:
        """Complete this onboarding session.

        Args:
            db_conn: Database connection
            timestamp: Completion timestamp
        """
        self.state = OnboardingState.COMPLETE.value
        self.completed_at = timestamp
        self.updated_at = timestamp
        db_conn.add(self)

    @traced(extract_args=[])
    async def inactivate_onboarding(self, db_conn: AsyncSession, *, timestamp: datetime) -> None:
        """Mark this onboarding session as inactive due to timeout.

        Args:
            db_conn: Database connection
            timestamp: Inactivation timestamp
        """
        self.state = OnboardingState.INCOMPLETE.value
        self.updated_at = timestamp
        db_conn.add(self)

    @classmethod
    async def get_by_user_id(
        cls,
        db_conn: AsyncSession,
        *,
        user_id: str,
    ) -> Optional["OnboardingSession"]:
        """Retrieve user onboarding state by user ID, ordered by most recent."""
        stmt = select(cls).where(cls.user_id == user_id).order_by(cls.created_at.desc())
        result = await db_conn.execute(stmt)
        return result.scalars().first()

    @classmethod
    async def get_by_session_key(
        cls,
        db_conn: AsyncSession,
        *,
        session_key: str,
    ) -> Optional["OnboardingSession"]:
        """Retrieve user onboarding state by session key."""
        stmt = select(cls).where(cls.session_key == session_key)
        result = await db_conn.execute(stmt)
        return result.scalars().one_or_none()
