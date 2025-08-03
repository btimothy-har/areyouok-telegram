import asyncio
import logging

from telegram.ext import Application
from telegram.ext import ContextTypes

from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database_session
from areyouok_telegram.jobs.conversations import schedule_conversation_job


async def restore_active_sessions(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Setup conversation jobs for active chats on startup."""
    async with async_database_session() as session:
        # Fetch all active sessions
        active_sessions = await Sessions.get_all_active_sessions(session)

        if not active_sessions:
            logging.info("No active sessions found, skipping conversation job setup.")
            return

        await asyncio.gather(
            *[
                schedule_conversation_job(
                    context=ctx,
                    chat_id=s.chat_id,
                )
                for s in active_sessions
            ]
        )
