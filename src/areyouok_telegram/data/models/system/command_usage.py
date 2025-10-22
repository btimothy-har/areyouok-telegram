"""CommandUsage Pydantic model for tracking command usage."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import logfire
import pydantic
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import CommandUsageTable
from areyouok_telegram.data.models.messaging.chat import Chat
from areyouok_telegram.utils.retry import db_retry


class CommandUsage(pydantic.BaseModel):
    """Model for tracking command usage."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Foreign keys
    chat: Chat
    command: str

    id: int = 0
    session_id: int | None = None
    timestamp: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))

    @property
    def object_key(self) -> str:
        """Generate a unique object key for a command usage based on chat ID, command, and timestamp."""
        timestamp_str = self.timestamp.isoformat()
        return hashlib.sha256(f"command_usage:{self.chat.id}:{self.command}:{timestamp_str}".encode()).hexdigest()

    @property
    def chat_id(self) -> int:
        """Get chat_id from the Chat object."""
        return self.chat.id

    @db_retry()
    async def save(self) -> CommandUsage:
        """Save the command usage to the database."""
        try:
            async with async_database() as db_conn:
                stmt = pg_insert(CommandUsageTable).values(
                    object_key=self.object_key,
                    chat_id=self.chat.id,
                    command=self.command,
                    session_id=self.session_id,
                    timestamp=self.timestamp,
                )

                result = await db_conn.execute(stmt)
                return result.rowcount

        # Catch exceptions here to avoid breaking application flow
        # This is a best-effort logging, so we log the exception but don't raise it
        except Exception as e:
            logfire.exception(f"Failed to save command usage record: {e}")
            return 0
