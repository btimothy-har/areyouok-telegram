from datetime import UTC
from datetime import datetime
from datetime import timedelta

import logfire
from telegram.ext import Application
from telegram.ext import ContextTypes

from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.jobs import ConversationJob
from areyouok_telegram.jobs import DataLogWarningJob
from areyouok_telegram.jobs import SessionCleanupJob
from areyouok_telegram.jobs import schedule_job


async def restore_active_sessions(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Setup conversation jobs for active chats on startup."""
    async with async_database() as db_conn:
        # Fetch all active sessions
        active_sessions = await Sessions.get_all_active_sessions(db_conn)

        if not active_sessions:
            logfire.info("No active sessions found, skipping conversation job setup.")
            return

        for session in active_sessions:
            await schedule_job(
                context=ctx,
                job=ConversationJob(chat_id=session.chat_id),
                interval=timedelta(seconds=10),
                first=datetime.now(UTC) + timedelta(seconds=5),
            )

    logfire.info(f"Restored {len(active_sessions)} active sessions.")


async def start_session_cleanups(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Start the session cleanup job."""
    # Schedule the job to run every hour, starting at the next 15-minute mark
    start_time = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(
        minutes=15 - datetime.now(UTC).minute % 15
    )

    await schedule_job(
        context=ctx,
        job=SessionCleanupJob(),
        interval=timedelta(minutes=15),  # Run every 15 minutes
        first=start_time,
    )


async def start_data_warning_job(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Start the data logging warning job."""
    # Schedule the job to run every hour, starting at the next 15-minute mark
    start_time = datetime.now(UTC) + timedelta(seconds=5)

    await schedule_job(
        context=ctx,
        job=DataLogWarningJob(),
        interval=timedelta(minutes=5),  # Run every 5 minutes
        first=start_time,
    )
