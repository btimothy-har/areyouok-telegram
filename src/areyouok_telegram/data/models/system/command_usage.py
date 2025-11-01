"""CommandUsage Pydantic model for tracking command usage."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import logfire
import pydantic
from sqlalchemy import select
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

    @classmethod
    @db_retry()
    async def get_by_id(cls, chat: Chat, *, command_usage_id: int) -> CommandUsage | None:
        """Retrieve a command usage record by its internal ID.

        Args:
            chat: Chat object
            command_usage_id: Internal command usage ID

        Returns:
            CommandUsage instance if found, None otherwise
        """
        async with async_database() as db_conn:
            stmt = select(CommandUsageTable).where(CommandUsageTable.id == command_usage_id)
            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return None

            return CommandUsage(
                id=row.id,
                chat=chat,
                command=row.command,
                session_id=row.session_id,
                timestamp=row.timestamp,
            )

    @db_retry()
    async def save(self) -> CommandUsage:
        """Save the command usage to the database.

        Returns:
            CommandUsage instance refreshed from database
        """
        try:
            async with async_database() as db_conn:
                stmt = (
                    pg_insert(CommandUsageTable)
                    .values(
                        object_key=self.object_key,
                        chat_id=self.chat.id,
                        command=self.command,
                        session_id=self.session_id,
                        timestamp=self.timestamp,
                    )
                    .returning(CommandUsageTable.id)
                )

                result = await db_conn.execute(stmt)
                row_id = result.scalar_one()

            # Return refreshed from database using get_by_id
            return await CommandUsage.get_by_id(chat=self.chat, command_usage_id=row_id)

        # Catch exceptions here to avoid breaking application flow
        # This is a best-effort logging, so we log the exception but don't raise it
        except Exception as e:
            logfire.exception(f"Failed to save command usage record: {e}")
            # Return self as fallback if save fails
            return self
