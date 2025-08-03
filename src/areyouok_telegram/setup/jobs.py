import asyncio
import logging
from datetime import UTC
from datetime import datetime
from datetime import timedelta

from telegram.ext import Application
from telegram.ext import ContextTypes

from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database_session
from areyouok_telegram.jobs import SessionCleanupJob
from areyouok_telegram.jobs import schedule_conversation_job

logger = logging.getLogger(__name__)


async def restore_active_sessions(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Setup conversation jobs for active chats on startup."""
    async with async_database_session() as session:
        # Fetch all active sessions
        active_sessions = await Sessions.get_all_active_sessions(session)

        if not active_sessions:
            logging.info("No active sessions found, skipping conversation job setup.")
            return

        await asyncio.gather(*[
            schedule_conversation_job(
                context=ctx,
                chat_id=s.chat_id,
            )
            for s in active_sessions
        ])


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

    logger.info(f"Scheduled session cleanup job to run every 15 minutes starting at {start_time.isoformat()}")
