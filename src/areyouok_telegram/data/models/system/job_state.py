"""JobState Pydantic model for persisting job execution state."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pydantic
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import JobStateTable
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import db_retry


class JobState(pydantic.BaseModel):
    """Model for persisting job execution state across restarts."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Job identification
    job_name: str

    # JSON state data - flexible schema for different job types
    state_data: dict

    # Metadata
    id: int = 0
    created_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))

    @property
    def object_key(self) -> str:
        """Generate a unique object key for a job based on its name."""
        return hashlib.sha256(f"job:{self.job_name}".encode()).hexdigest()

    @classmethod
    @traced(extract_args=["job_name"])
    @db_retry()
    async def get(cls, *, job_name: str) -> JobState | None:
        """Retrieve the JobState instance for a job.

        Args:
            job_name: Unique name of the job

        Returns:
            JobState instance, or None if no state exists
        """
        async with async_database() as db_conn:
            stmt = select(JobStateTable).where(JobStateTable.job_name == job_name)
            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row:
                return cls.model_validate(row, from_attributes=True)

            return None

    @traced()
    @db_retry()
    async def save(self) -> JobState:
        """Save or update the state for a job.

        Returns:
            JobState instance refreshed from database
        """
        async with async_database() as db_conn:
            stmt = (
                pg_insert(JobStateTable)
                .values(
                    object_key=self.object_key,
                    job_name=self.job_name,
                    state_data=self.state_data,
                    created_at=self.created_at,
                    updated_at=self.updated_at,
                )
                .on_conflict_do_update(
                    index_elements=["object_key"],
                    set_={
                        "state_data": self.state_data,
                        "updated_at": self.updated_at,
                    },
                )
                .returning(JobStateTable)
            )

            result = await db_conn.execute(stmt)
            row = result.scalar_one()

            return JobState.model_validate(row, from_attributes=True)

    @traced()
    @db_retry()
    async def delete(self) -> None:
        """Delete the state for a job."""
        async with async_database() as db_conn:
            stmt = select(JobStateTable).where(JobStateTable.object_key == self.object_key)
            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row:
                await db_conn.delete(row)
