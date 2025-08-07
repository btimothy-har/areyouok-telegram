from datetime import datetime
from datetime import timedelta

import logfire
from telegram.ext import ContextTypes

from areyouok_telegram.data import Messages
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.jobs import BaseJob
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import traced

from .utils import get_all_inactive_sessions


class SessionCleanupJob(BaseJob):
    """
    Application lifecycle job for cleaning up sessions.

    This job:
    1. Fetches recently-ended sessions
    2. Deletes messages associated with those sessions
    3. Cleans up any other session-related data as needed
    """

    def __init__(self):
        """
        Initialize the session cleanup job.
        """
        super().__init__()
        self.last_cleanup_timestamp: datetime | None = None

    @property
    def name(self) -> str:
        return "session_cleanup"

    @traced(extract_args=False)
    async def _run(self, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        """Process conversation for this chat."""

        if not self.last_cleanup_timestamp:
            cleanup_since = self._run_timestamp - timedelta(days=7)
        else:
            cleanup_since = self.last_cleanup_timestamp

        sessions = await get_all_inactive_sessions(
            from_dt=cleanup_since,
            to_dt=self._run_timestamp - timedelta(minutes=10),  # Safety margin of 10 minutes
        )

        if not sessions:
            logfire.info("No inactive sessions found for cleanup.")
            return

        with logfire.span(
            f"Cleaning up {len(sessions)} inactive sessions since {cleanup_since.isoformat()}",
        ):
            total_deleted = 0

            for session in sessions:
                deleted_count = await self._cleanup_session(session)
                total_deleted += deleted_count

            logfire.info(f"Session cleanup completed. Deleted {total_deleted} messages from {len(sessions)} sessions.")

            # Update the last cleanup timestamp
            self.last_cleanup_timestamp = self._run_timestamp

    @db_retry()
    async def _cleanup_session(self, chat_session: Sessions) -> int:
        """Clean up messages for a specific chat session."""

        async with async_database() as db_conn:
            messages = await Messages.retrieve_raw_by_chat(
                db_conn=db_conn,
                chat_id=chat_session.chat_id,
                to_time=chat_session.session_end,
            )

            ct = 0
            for msg in messages:
                deleted = await msg.delete(db_conn=db_conn)
                ct += 1 if deleted else 0

            logfire.info(
                f"Cleaned up {ct} messages for session {chat_session.session_id} in chat {chat_session.chat_id}."
            )
            return ct
