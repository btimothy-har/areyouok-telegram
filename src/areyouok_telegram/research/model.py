import random
from datetime import UTC
from datetime import datetime

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

from .studies.personality_scenarios import PERSONALITY_SCENARIOS


class ResearchScenario(Base):
    __tablename__ = "scenarios"
    __table_args__ = {"schema": "research"}

    session_key = Column(String, ForeignKey(f"{ENV}.sessions.session_key"), nullable=False, unique=True)
    scenario_config = Column(String, nullable=False)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @property
    def session_id(self) -> str:
        """Return the unique session ID, which is the session key."""
        return self.session_key

    @classmethod
    @traced(extract_args=["session_id"], record_return=True)
    async def generate_for_session(
        cls,
        db_conn: AsyncSession,
        session_id: str,
    ) -> "ResearchScenario":
        """Insert a research scenario for a session, or return existing if already present.

        Args:
            db_conn: The database connection to use for the query.
            session_id: The unique session identifier to associate the scenario with.

        Returns:
            The ResearchScenario object, either newly created or existing.
        """
        now = datetime.now(UTC)

        random_scenario = random.choice(list(PERSONALITY_SCENARIOS.keys()))

        stmt = pg_insert(cls).values(
            session_key=session_id,
            scenario_config=random_scenario,
            created_at=now,
        )

        # On conflict, update the created_at timestamp to ensure we always return something
        # This handles race conditions where the same session scenario might be created twice
        stmt = stmt.on_conflict_do_update(
            index_elements=["session_key"],
            set_={"created_at": now},  # Update timestamp to latest attempt
        ).returning(cls)

        result = await db_conn.execute(stmt)
        return result.scalar_one()  # Always returns the scenario object

    @classmethod
    @traced(extract_args=["session_id"])
    async def get_for_session_id(
        cls,
        db_conn: AsyncSession,
        session_id: str,
    ) -> list["ResearchScenario"] | None:
        """Retrieve the assigned research scenario by session_id."""

        stmt = select(cls).where(cls.session_key == session_id)
        result = await db_conn.execute(stmt)

        scenario = result.scalars().one_or_none()

        return scenario if scenario else None
