from datetime import datetime, timedelta

import logfire
from telegram.ext import ContextTypes

from areyouok_telegram.jobs.base import JOB_LOCK, BaseJob


async def schedule_job(
    context: ContextTypes.DEFAULT_TYPE, job: BaseJob, interval: timedelta, first: datetime, job_kwargs: dict = None
):
    """
    Helper function to schedule a repeating job in the job queue.
    """

    job_kwargs = job_kwargs or {}

    async with JOB_LOCK[job.id]:
        existing_jobs = context.job_queue.get_jobs_by_name(job.name)
        if existing_jobs:
            logfire.debug(f"Job {job.name} already exists.")
            return

        # Schedule the job to run once after the specified delay
        context.job_queue.run_repeating(
            callback=job.run,
            interval=interval,
            first=first,
            name=job.name,
            job_kwargs={
                "id": job.id,
                "coalesce": job_kwargs.get("coalesce", True),
                "max_instances": job_kwargs.get("max_instances", 1),
                **job_kwargs,
            },
        )

    logfire.info(
        f"Scheduled job {job.name} with interval {interval}. First run: {first.isoformat()}.",
        job_class=job.__class__.__name__,
        job_id=job.id,
        interval=interval,
        first=first,
        kwargs=job_kwargs,
    )


async def run_job_once(
    context: ContextTypes.DEFAULT_TYPE,
    job: BaseJob,
    when: datetime,
    job_kwargs: dict = None,
):
    context.job_queue.run_once(
        callback=job.run,
        when=when,
        name=job.name,
        job_kwargs={
            "id": job.id,
            "coalesce": job_kwargs.get("coalesce", True) if job_kwargs else True,
            "max_instances": job_kwargs.get("max_instances", 1) if job_kwargs else 1,
            **(job_kwargs or {}),
        },
    )

    logfire.info(
        f"Scheduled one-time job {job.name} to run at {when.isoformat()}.",
        job_class=job.__class__.__name__,
        job_id=job.id,
        when=when,
        kwargs=job_kwargs,
    )
