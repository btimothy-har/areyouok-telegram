import asyncio
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import logfire
from telegram.ext import Application
from telegram.ext import ContextTypes

from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.jobs import SessionCleanupJob
from areyouok_telegram.jobs import schedule_conversation_job


async def restore_active_sessions(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Setup conversation jobs for active chats on startup."""
    with logfire.span(
        "Restoring chat sessions from database.",
        _span_name="setup.jobs.restore_active_sessions",
    ):
        async with async_database() as db_conn:
            # Fetch all active sessions
            active_sessions = await Sessions.get_all_active_sessions(db_conn)

            if not active_sessions:
                logfire.info("No active sessions found, skipping conversation job setup.")
                return

            await asyncio.gather(*[
                schedule_conversation_job(
                    context=ctx,
                    chat_id=s.chat_id,
                )
                for s in active_sessions
            ])

        logfire.info(f"Restored {len(active_sessions)} active sessions.")


async def start_session_cleanups(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Start the session cleanup job."""
    job = SessionCleanupJob()

    # Schedule the job to run every hour, starting at the next 15-minute mark
    start_time = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(
        minutes=15 - datetime.now(UTC).minute % 15
    )

    ctx.job_queue.run_repeating(
        job.run,
        interval=15 * 60,  # Run every 15 minutes
        first=start_time,
        name=job.name,
        job_kwargs={
            "id": job._id,
            "coalesce": True,
            "max_instances": 1,
        },
    )

    logfire.info(f"Session cleanup job scheduled to run every 15 minutes starting at {start_time.isoformat()}.")
