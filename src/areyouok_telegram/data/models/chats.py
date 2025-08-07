import hashlib
from datetime import UTC
from datetime import datetime

import telegram
from sqlalchemy import BOOLEAN
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.utils import traced


class Chats(Base):
    __tablename__ = "chats"
    __table_args__ = {"schema": ENV}

    chat_key = Column(String, nullable=False, unique=True)

    chat_id = Column(String, nullable=False)
    type = Column(String, nullable=False)
    title = Column(String, nullable=True)
    is_forum = Column(BOOLEAN, nullable=False)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_chat_key(chat_id: str) -> str:
        """Generate a unique key for a chat based on its chat ID."""
        return hashlib.sha256(f"{chat_id}".encode()).hexdigest()

    @classmethod
    @traced(extract_args=["chat"])
    async def new_or_update(cls, db_conn: AsyncSession, chat: telegram.Chat):
        """Insert or update a chat in the database."""
        now = datetime.now(UTC)

        stmt = pg_insert(cls).values(
            chat_key=cls.generate_chat_key(str(chat.id)),
            chat_id=str(chat.id),
            type=chat.type,
            title=chat.title,
            is_forum=chat.is_forum if chat.is_forum is not None else False,
            created_at=now,
            updated_at=now,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["chat_key"],
            set_={
                "type": stmt.excluded.type,
                "title": stmt.excluded.title,
                "is_forum": stmt.excluded.is_forum,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await db_conn.execute(stmt)
