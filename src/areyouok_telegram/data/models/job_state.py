"""Database model for persisting job execution state across restarts."""

import hashlib
from datetime import UTC
from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select
from sqlalchemy.sql import update

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.logging import traced


class JobState(Base):
    """Store persistent state for background jobs.

    This table tracks execution state for jobs that need to persist information
    across bot restarts (e.g., last_run_time for batch processing jobs).
    """

    __tablename__ = "job_state"
    __table_args__ = {"schema": ENV}

    job_key = Column(String, nullable=False, unique=True, index=True)
    job_name = Column(String, nullable=False, index=True)

    # JSON state data - flexible schema for different job types
    state_data = Column(JSONB, nullable=False, default={})

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_job_key(job_name: str) -> str:
        """Generate a unique key for a job based on its name."""
        return hashlib.sha256(f"job:{job_name}".encode()).hexdigest()

    @classmethod
    @traced(extract_args=["job_name"])
    async def get_state(cls, db_conn: AsyncSession, *, job_name: str) -> dict | None:
        """Retrieve the current state for a job.

        Args:
            db_conn: Database connection
            job_name: Unique name of the job

        Returns:
            Dictionary of state data, or None if no state exists
        """
        job_key = cls.generate_job_key(job_name)

        stmt = select(cls).where(cls.job_key == job_key)
        result = await db_conn.execute(stmt)
        job_state = result.scalar_one_or_none()

        if job_state:
            return job_state.state_data

        return None

    @classmethod
    @traced(extract_args=["job_name"])
    async def save_state(cls, db_conn: AsyncSession, *, job_name: str, state_data: dict) -> "JobState":
        """Save or update the state for a job.

        Args:
            db_conn: Database connection
            job_name: Unique name of the job
            state_data: Dictionary of state data to persist

        Returns:
            JobState record
        """
        job_key = cls.generate_job_key(job_name)
        now = datetime.now(UTC)

        stmt = (
            pg_insert(cls)
            .values(
                job_key=job_key,
                job_name=job_name,
                state_data=state_data,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["job_key"],
                set_={
                    "state_data": state_data,
                    "updated_at": now,
                },
            )
            .returning(cls)
        )

        result = await db_conn.execute(stmt)
        return result.scalar_one()

    @classmethod
    @traced(extract_args=["job_name"])
    async def update_state(cls, db_conn: AsyncSession, *, job_name: str, **kwargs) -> None:
        """Update specific fields in the job state.

        Args:
            db_conn: Database connection
            job_name: Unique name of the job
            **kwargs: Key-value pairs to update in state_data
        """
        job_key = cls.generate_job_key(job_name)
        now = datetime.now(UTC)

        # Get current state
        current_state = await cls.get_state(db_conn, job_name=job_name)
        if current_state is None:
            current_state = {}

        # Merge with new values
        updated_state = {**current_state, **kwargs}

        stmt = (
            update(cls)
            .where(cls.job_key == job_key)
            .values(
                state_data=updated_state,
                updated_at=now,
            )
        )

        await db_conn.execute(stmt)

    @classmethod
    @traced(extract_args=["job_name"])
    async def delete_state(cls, db_conn: AsyncSession, *, job_name: str) -> None:
        """Delete the state for a job.

        Args:
            db_conn: Database connection
            job_name: Unique name of the job
        """
        job_key = cls.generate_job_key(job_name)

        stmt = select(cls).where(cls.job_key == job_key)
        result = await db_conn.execute(stmt)
        job_state = result.scalar_one_or_none()

        if job_state:
            await db_conn.delete(job_state)
