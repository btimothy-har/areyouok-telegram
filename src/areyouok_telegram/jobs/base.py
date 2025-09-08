import asyncio
import hashlib
from abc import ABC
from abc import abstractmethod
from collections import defaultdict
from datetime import UTC
from datetime import datetime

import logfire
from telegram.ext import ContextTypes

from areyouok_telegram.logging import traced

JOB_LOCK = defaultdict(asyncio.Lock)


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
        self._run_timestamp = datetime.now(UTC)
        self._run_count = 0

    @property
    def id(self) -> str:
        return hashlib.md5(self.name.encode()).hexdigest()

    async def run(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Runs the job. This method should be called by the job scheduler.
        """
        self._run_count += 1
        self._run_timestamp = datetime.now(UTC)
        self._bot_id = context.bot.id

        await self._run(context)

    @traced(extract_args=False)
    async def stop(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Stops the job gracefully.
        """
        async with JOB_LOCK[self.id]:
            existing_jobs = context.job_queue.get_jobs_by_name(self.name)
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
    async def _run(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Internal method to run the job. This should be overridden by subclasses to implement the job's logic.
        """
        raise NotImplementedError("Subclasses must implement the '_run' method.")
