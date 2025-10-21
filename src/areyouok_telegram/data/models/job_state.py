"""JobState Pydantic model for persisting job execution state."""

import hashlib
from datetime import UTC, datetime

import pydantic
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import JobStateTable
from areyouok_telegram.logging import traced


class JobState(pydantic.BaseModel):
    """Model for persisting job execution state across restarts."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Internal ID
    id: int

    # Job identification
    job_name: str

    # JSON state data - flexible schema for different job types
    state_data: dict

    # Metadata
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def generate_object_key(job_name: str) -> str:
        """Generate a unique object key for a job based on its name."""
        return hashlib.sha256(f"job:{job_name}".encode()).hexdigest()

    @classmethod
    @traced(extract_args=["job_name"])
    async def get_state(cls, *, job_name: str) -> dict | None:
        """Retrieve the current state for a job.

        Args:
            job_name: Unique name of the job

        Returns:
            Dictionary of state data, or None if no state exists
        """
        object_key = cls.generate_object_key(job_name)

        async with async_database() as db_conn:
            stmt = select(JobStateTable).where(JobStateTable.object_key == object_key)
            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row:
                return row.state_data

            return None

    @classmethod
    @traced(extract_args=["job_name"])
    async def save_state(cls, *, job_name: str, state_data: dict) -> "JobState":
        """Save or update the state for a job.

        Args:
            job_name: Unique name of the job
            state_data: Dictionary of state data to persist

        Returns:
            JobState instance
        """
        object_key = cls.generate_object_key(job_name)
        now = datetime.now(UTC)

        async with async_database() as db_conn:
            stmt = (
                pg_insert(JobStateTable)
                .values(
                    object_key=object_key,
                    job_name=job_name,
                    state_data=state_data,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["object_key"],
                    set_={
                        "state_data": state_data,
                        "updated_at": now,
                    },
                )
                .returning(JobStateTable)
            )

            result = await db_conn.execute(stmt)
            row = result.scalar_one()

            return cls.model_validate(row, from_attributes=True)

    @classmethod
    @traced(extract_args=["job_name"])
    async def delete_state(cls, *, job_name: str) -> None:
        """Delete the state for a job.

        Args:
            job_name: Unique name of the job
        """
        object_key = cls.generate_object_key(job_name)

        async with async_database() as db_conn:
            stmt = select(JobStateTable).where(JobStateTable.object_key == object_key)
            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row:
                await db_conn.delete(row)
