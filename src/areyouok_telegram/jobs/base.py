import asyncio
import hashlib
from abc import ABC
from abc import abstractmethod
from collections import defaultdict
from datetime import UTC
from datetime import datetime

import logfire
from telegram.ext import ContextTypes

from areyouok_telegram.data import JobState
from areyouok_telegram.data import async_database
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import db_retry

JOB_LOCK = defaultdict(asyncio.Lock)


class RunContextNotInitializedError(RuntimeError):
    def __init__(self, job_name: str):
        super().__init__(f"Run context not initialized for job: {job_name}.")


class BaseJob(ABC):
    """
    Base class for all jobs in the areyouok-telegram application.
    Provides a common interface for job execution and error handling.
    """

    def __init__(self):
        """
        Initializes the BaseJob instance.
        This constructor can be extended by subclasses to initialize additional attributes.
        """
        self._bot_id = None
        self._run_timestamp: datetime = datetime.now(UTC)

        self._run_context: ContextTypes.DEFAULT_TYPE | None = None
        self._run_count: int = 0

    @property
    def id(self) -> str:
        return hashlib.md5(self.name.encode()).hexdigest()

    async def run(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Runs the job. This method should be called by the job scheduler.
        """
        self._run_count += 1
        self._run_timestamp = datetime.now(UTC)

        self._run_context = context
        self._bot_id = context.bot.id

        await self.run_job()

    @traced(extract_args=False)
    async def stop(self) -> None:
        """
        Stops the job gracefully.
        """
        if self._run_context is None:
            raise RunContextNotInitializedError(self.name)

        async with JOB_LOCK[self.id]:
            existing_jobs = self._run_context.job_queue.get_jobs_by_name(self.name)
            if not existing_jobs:
                logfire.warning(f"No existing job found for {self.name}, nothing to stop.")
                return

            for job in existing_jobs:
                job.schedule_removal()

        logfire.info(f"Scheduled job {self.name} is now stopped.")

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Abstract property to be implemented by subclasses to provide a unique name for the job.
        This name is used to identify the job and can be used for logging or scheduling purposes.
        """
        raise NotImplementedError("Subclasses must implement the 'name' property.")

    @abstractmethod
    async def run_job(self) -> None:
        """
        Internal method to run the job. This should be overridden by subclasses to implement the job's logic.
        """
        raise NotImplementedError("Subclasses must implement the 'run_job' method.")

    @traced(extract_args=["state_data"])
    @db_retry()
    async def save_state(self, **state_data) -> None:
        """
        Save job state to the database.

        This method persists job execution state (e.g., last_run_time) to the database,
        ensuring state survives bot restarts.

        Args:
            **state_data: Key-value pairs to store in job state.
                         Values should be JSON-serializable.

        Example:
            await self.save_state(
                last_run_time=datetime.now(UTC).isoformat(),
                processed_count=100
            )
        """
        async with async_database() as db_conn:
            await JobState.save_state(db_conn, job_name=self.name, state_data=state_data)

        logfire.debug(f"Saved state for job {self.name}", state_keys=list(state_data.keys()))

    @traced(extract_args=False)
    @db_retry()
    async def load_state(self) -> dict:
        """
        Load job state from the database.

        Returns:
            Dictionary of persisted state data, or empty dict if no state exists.

        Example:
            state = await self.load_state()
            last_run_time = state.get('last_run_time')
            if last_run_time:
                last_run_time = datetime.fromisoformat(last_run_time)
        """
        async with async_database() as db_conn:
            state = await JobState.get_state(db_conn, job_name=self.name)

        if state:
            logfire.debug(f"Loaded state for job {self.name}", state_keys=list(state.keys()))
            return state

        logfire.debug(f"No state found for job {self.name}, returning empty dict")
        return {}

    @traced(extract_args=False)
    @db_retry()
    async def clear_state(self) -> None:
        """
        Clear persisted job state from the database.

        This is useful for resetting a job's state or during cleanup.
        """
        async with async_database() as db_conn:
            await JobState.delete_state(db_conn, job_name=self.name)

        logfire.info(f"Cleared state for job {self.name}")
