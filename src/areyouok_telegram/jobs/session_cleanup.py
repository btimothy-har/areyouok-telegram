import hashlib
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import logfire
from telegram.ext import ContextTypes

from areyouok_telegram.data import Messages
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database_session


class SessionCleanupJob:
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
        self.last_cleanup_timestamp: datetime | None = None

    @property
    def name(self) -> str:
        """Generate a consistent job name for this chat."""
        return "session_cleanup"

    @property
    def _id(self) -> str:
        return hashlib.md5(self.name.encode()).hexdigest()

    async def run(self, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        """Process conversation for this chat."""

        runtime = datetime.now(UTC)

        if not self.last_cleanup_timestamp:
            cleanup_since = runtime - timedelta(days=7)
        else:
            cleanup_since = self.last_cleanup_timestamp

        with logfire.span(
            "Session cleanup job running",
            _span_name="jobs.session_cleanup.run",
            since=cleanup_since,
            runtime=runtime,
        ):
            async with async_database_session() as conn:
                # Fetch all inactive sessions that ended after the last cleanup timestamp
                # We only want sessions that have been inactive for at least 10 minutes as a safety margin
                sessions = await Sessions.get_all_inactive_sessions(
                    conn, from_dt=cleanup_since, to_dt=runtime - timedelta(minutes=10)
                )

                if not sessions:
                    logfire.debug("No inactive sessions found for cleanup.")
                    return

            with logfire.span(
                f"Cleaning up {len(sessions)} inactive sessions since {cleanup_since.isoformat()}",
            ):
                total_deleted = 0

                for session in sessions:
                    deleted_count = await self._cleanup_session(session)
                    total_deleted += deleted_count

                logfire.info(
                    f"Session cleanup completed. Deleted {total_deleted} messages from {len(sessions)} sessions."
                )

                # Update the last cleanup timestamp
                self.last_cleanup_timestamp = runtime

    async def _cleanup_session(self, chat_session: Sessions) -> bool:
        """Process messages for this chat and send appropriate replies.

        Returns:
            bool: True if action was taken (message sent), False otherwise
        """

        # Run this using a separate connector to avoid collisions
        async with async_database_session() as conn:
            messages = await Messages.retrieve_raw_by_chat(
                session=conn,
                chat_id=chat_session.chat_id,
                to_time=chat_session.session_end,
            )

            ct = 0
            for msg in messages:
                deleted = await msg.delete()
                ct += 1 if deleted else 0

        logfire.info(f"Cleaned up {ct} messages for session {chat_session.session_id} in chat {chat_session.chat_id}.")

        return ct
