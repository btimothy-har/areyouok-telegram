from datetime import UTC, datetime

import logfire
from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.logging import traced


class CommandUsage(Base):
    __tablename__ = "command_usage"
    __table_args__ = {"schema": ENV}

    command = Column(String, nullable=False)
    chat_id = Column(String, nullable=False)
    session_id = Column(String, nullable=True)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False)

    id = Column(Integer, primary_key=True, autoincrement=True)

    @classmethod
    @traced(extract_args=["command", "chat_id", "session_id"])
    async def track_command(
        cls,
        db_conn: AsyncSession,
        *,
        command: str,
        chat_id: str,
        session_id: str | None = None,
    ) -> int:
        """Track command usage in the database.

        This is a best-effort logging function that won't raise exceptions
        to avoid breaking the application flow.

        Args:
            db_conn: Database connection
            command: Command name (e.g., "start", "preferences")
            chat_id: Chat identifier
            session_id: Session identifier

        Returns:
            int: Number of rows inserted (0 if failed)
        """
        try:
            now = datetime.now(UTC)

            stmt = pg_insert(cls).values(
                command=command,
                chat_id=str(chat_id),
                session_id=session_id,
                timestamp=now,
            )

            result = await db_conn.execute(stmt)

        # Catch exceptions here to avoid breaking application flow
        # This is a best-effort logging, so we log the exception but don't raise it
        except Exception as e:
            logfire.exception(f"Failed to insert command usage record: {e}")
            return 0
        else:
            return result.rowcount
