"""Notification Pydantic model for pending notifications."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pydantic
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import NotificationsTable
from areyouok_telegram.data.models.messaging.chat import Chat
from areyouok_telegram.logging import traced


class Notification(pydantic.BaseModel):
    """Notification model for pending notifications."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Required fields
    chat_id: int
    content: str

    # Optional fields
    id: int = 0
    priority: int = 2
    created_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    processed_at: datetime | None = None

    @property
    def object_key(self) -> str:
        """Generate a unique object key for a notification."""
        return hashlib.sha256(
            f"notification:{self.chat_id}:{self.content}:{self.created_at.isoformat()}".encode()
        ).hexdigest()

    @property
    def status(self) -> str:
        """Return status based on processed_at."""
        return "pending" if self.processed_at is None else "completed"

    @traced()
    async def save(self) -> Notification:
        """Save or update the notification in the database.

        Returns:
            Notification instance refreshed from database
        """
        now = datetime.now(UTC)

        async with async_database() as db_conn:
            stmt = pg_insert(NotificationsTable).values(
                object_key=self.object_key,
                chat_id=self.chat_id,
                content=self.content,
                priority=self.priority,
                created_at=self.created_at,
                updated_at=now,
                processed_at=self.processed_at,
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=["object_key"],
                set_={
                    "content": stmt.excluded.content,
                    "priority": stmt.excluded.priority,
                    "processed_at": stmt.excluded.processed_at,
                    "updated_at": stmt.excluded.updated_at,
                },
            ).returning(NotificationsTable)

            result = await db_conn.execute(stmt)
            row = result.scalar_one()

            return Notification.model_validate(row, from_attributes=True)

    @classmethod
    @traced(extract_args=["chat"])
    async def get_next_pending(
        cls,
        chat: Chat,
    ) -> Notification | None:
        """Get the next pending notification for a chat, ordered by priority then created_at.

        Args:
            chat: Chat object

        Returns:
            The next pending notification, or None if no pending notifications exist
        """
        async with async_database() as db_conn:
            stmt = (
                select(NotificationsTable)
                .where(NotificationsTable.chat_id == chat.id, NotificationsTable.processed_at.is_(None))
                .order_by(NotificationsTable.priority.asc(), NotificationsTable.created_at.asc())
                .limit(1)
            )

            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return None

            return Notification.model_validate(row, from_attributes=True)

    @traced()
    async def mark_as_completed(self) -> Notification:
        """Mark notification as completed by setting processed_at timestamp and saving.

        Returns:
            Updated Notification instance
        """
        self.processed_at = datetime.now(UTC)
        return await self.save()
