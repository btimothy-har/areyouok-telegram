import hashlib
from datetime import UTC
from datetime import datetime

import telegram
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data.connection import Base
from areyouok_telegram.data.utils import with_retry


class Messages(Base):
    __tablename__ = "messages"
    __table_args__ = {"schema": ENV}

    num = Column(Integer, primary_key=True, autoincrement=True)
    message_key = Column(String, nullable=False, unique=True)
    message_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    chat_id = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_message_key(user_id: str, chat_id: str, message_id: int) -> str:
        """Generate a unique key for a message based on user ID, chat ID, and message ID."""
        return hashlib.sha256(f"{user_id}:{chat_id}:{message_id}".encode()).hexdigest()

    @classmethod
    @with_retry()
    async def new_or_update(cls, session: AsyncSession, user_id: str, chat_id: str, message: telegram.Message):
        """Insert or update a message in the database."""
        now = datetime.now(UTC)

        message_key = cls.generate_message_key(user_id, chat_id, message.message_id)

        stmt = pg_insert(cls).values(
            message_key=message_key,
            message_id=str(message.message_id),
            user_id=str(user_id),
            chat_id=str(chat_id),
            payload=message.to_dict(),
            created_at=now,
            updated_at=now,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["message_key"],
            set_={
                "payload": stmt.excluded.payload,
                "updated_at": stmt.excluded.updated_at,
            },
        )

        await session.execute(stmt)
