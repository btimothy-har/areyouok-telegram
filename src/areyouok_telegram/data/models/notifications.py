from __future__ import annotations

import hashlib
from datetime import UTC
from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.utils import traced


class Notifications(Base):
    __tablename__ = "notifications"
    __table_args__ = {"schema": ENV}

    notification_key = Column(String, nullable=False, unique=True)

    chat_id = Column(String, nullable=False, index=True)
    content = Column(String, nullable=False)
    priority = Column(Integer, nullable=False, default=2)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)
    processed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    @staticmethod
    def generate_notification_key(chat_id: str, content: str, created_at: datetime) -> str:
        """Generate a unique key for a notification based on chat ID, content, and created_at."""
        return hashlib.sha256(f"{chat_id}:{content}:{created_at.isoformat()}".encode()).hexdigest()

    @property
    def status(self) -> str:
        """Return status based on processed_at."""
        return "pending" if self.processed_at is None else "completed"

    @classmethod
    @traced(extract_args=["chat_id", "content", "priority"])
    async def add(
        cls,
        db_conn: AsyncSession,
        *,
        chat_id: str,
        content: str,
        priority: int = 2,
    ) -> None:
        """Create a new notification.

        Args:
            db_conn: Database connection
            chat_id: Chat ID for the notification
            content: Notification content
            priority: Priority level (1=high, 2=medium, 3=low)
        """
        now = datetime.now(UTC)

        notification_key = cls.generate_notification_key(chat_id, content, now)

        stmt = pg_insert(cls).values(
            notification_key=notification_key,
            chat_id=str(chat_id),
            content=content,
            priority=priority,
            created_at=now,
            updated_at=now,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["notification_key"],
            set_={
                "content": stmt.excluded.content,
                "priority": stmt.excluded.priority,
                "updated_at": stmt.excluded.updated_at,
            },
        )

        await db_conn.execute(stmt)

    @classmethod
    @traced(extract_args=["chat_id"])
    async def get_next_pending(
        cls,
        db_conn: AsyncSession,
        *,
        chat_id: str,
    ) -> Notifications | None:
        """Get the next pending notification for a chat, ordered by priority then created_at.

        Args:
            db_conn: Database connection
            chat_id: Chat ID to get notifications for

        Returns:
            The next pending notification, or None if no pending notifications exist
        """
        stmt = (
            select(cls)
            .where(cls.chat_id == chat_id, cls.processed_at.is_(None))
            .order_by(cls.priority.asc(), cls.created_at.asc())
            .limit(1)
        )

        result = await db_conn.execute(stmt)
        return result.scalar_one_or_none()

    @traced(extract_args=["notification_key"])
    async def mark_as_completed(self, db_conn: AsyncSession) -> None:
        """Mark notification as completed by setting processed_at timestamp.

        Args:
            db_conn: Database connection
        """
        now = datetime.now(UTC)
        self.processed_at = now
        self.updated_at = now
        db_conn.add(self)
