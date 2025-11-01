"""JobState Pydantic model for persisting job execution state."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pydantic
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import JobStateTable
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
    @db_retry()
    async def get_by_id(cls, *, job_state_id: int) -> JobState | None:
        """Retrieve a job state by its internal ID.

        Args:
            job_state_id: Internal job state ID

        Returns:
            JobState instance if found, None otherwise
        """
        async with async_database() as db_conn:
            stmt = select(JobStateTable).where(JobStateTable.id == job_state_id)
            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return None

            return cls.model_validate(row, from_attributes=True)

    @classmethod
    @db_retry()
    async def get(cls, *, job_name: str) -> JobState | None:
        """Retrieve the JobState instance for a job by name.

        Args:
            job_name: Unique name of the job

        Returns:
            JobState instance, or None if no state exists
        """
        # Query for ID only
        async with async_database() as db_conn:
            stmt = select(JobStateTable.id).where(JobStateTable.job_name == job_name)
            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return None

        # Hydrate via get_by_id
        return await cls.get_by_id(job_state_id=row)

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
                    index_elements=["job_name"],
                    set_={
                        "state_data": self.state_data,
                        "updated_at": self.updated_at,
                    },
                )
                .returning(JobStateTable.id)
            )

            result = await db_conn.execute(stmt)
            row_id = result.scalar_one()

        # Return via get_by_id for consistent hydration
        return await JobState.get_by_id(job_state_id=row_id)

    @db_retry()
    async def delete(self) -> None:
        """Delete the state for a job."""
        async with async_database() as db_conn:
            stmt = sql_delete(JobStateTable).where(JobStateTable.job_name == self.job_name)
            await db_conn.execute(stmt)
