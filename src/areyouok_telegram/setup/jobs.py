from datetime import UTC, datetime, timedelta

import logfire
from telegram.ext import Application, ContextTypes

from areyouok_telegram.config import PROFILE_JOB_INTERVAL_SECS, RAG_JOB_INTERVAL_SECS
from areyouok_telegram.data import Sessions, async_database
from areyouok_telegram.jobs import (
    ContextEmbeddingJob,
    ConversationJob,
    DataLogWarningJob,
    PingJob,
    ProfileGenerationJob,
    schedule_job,
)


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
                interval=timedelta(seconds=5),
                first=datetime.now(UTC) + timedelta(seconds=5),
            )

    logfire.info(f"Restored {len(active_sessions)} active sessions.")


async def start_context_embedding_job(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Start the context embedding job."""
    await schedule_job(
        context=ctx,
        job=ContextEmbeddingJob(),
        interval=timedelta(seconds=RAG_JOB_INTERVAL_SECS),
        first=datetime.now(UTC) + timedelta(seconds=60),
    )


async def start_profile_generation_job(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Start the profile generation job."""
    await schedule_job(
        context=ctx,
        job=ProfileGenerationJob(),
        interval=timedelta(seconds=PROFILE_JOB_INTERVAL_SECS),
        first=datetime.now(UTC) + timedelta(seconds=300),  # Start 5 minutes after startup
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


async def start_ping_job(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Start the ping job to run at the top of every hour."""
    # Calculate the next top of the hour
    now = datetime.now(UTC)
    # Move to the next hour and zero out minutes/seconds/microseconds
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    await schedule_job(
        context=ctx,
        job=PingJob(),
        interval=timedelta(hours=1),  # Run every hour
        first=next_hour,
    )
