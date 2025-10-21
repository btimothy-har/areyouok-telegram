"""CommandUsage Pydantic model for tracking command usage."""

from datetime import UTC, datetime

import logfire
import pydantic
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import CommandUsageTable
from areyouok_telegram.logging import traced


class CommandUsage(pydantic.BaseModel):
    """Model for tracking command usage."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Internal ID
    id: int

    # Foreign keys
    chat_id: int
    session_id: int | None = None

    # Command data
    command: str
    timestamp: datetime

    @classmethod
    @traced(extract_args=["command", "chat_id", "session_id"])
    async def track_command(
        cls,
        *,
        command: str,
        chat_id: int,
        session_id: int | None = None,
    ) -> int:
        """Track command usage in the database.

        This is a best-effort logging function that won't raise exceptions
        to avoid breaking the application flow.

        Args:
            command: Command name (e.g., "start", "preferences")
            chat_id: Internal chat ID (FK to chats.id)
            session_id: Internal session ID (FK to sessions.id)

        Returns:
            int: Number of rows inserted (0 if failed)
        """
        try:
            now = datetime.now(UTC)

            async with async_database() as db_conn:
                stmt = pg_insert(CommandUsageTable).values(
                    command=command,
                    chat_id=chat_id,
                    session_id=session_id,
                    timestamp=now,
                )

                result = await db_conn.execute(stmt)
                return result.rowcount

        # Catch exceptions here to avoid breaking application flow
        # This is a best-effort logging, so we log the exception but don't raise it
        except Exception as e:
            logfire.exception(f"Failed to insert command usage record: {e}")
            return 0
