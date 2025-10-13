import hashlib
from datetime import UTC, datetime

import telegram
from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.logging import traced


class Updates(Base):
    __tablename__ = "updates"
    __table_args__ = {"schema": ENV}

    update_key = Column(String, nullable=False, unique=True)

    update_id = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_update_key(payload: str) -> str:
        """Generate a unique key for an update based on its payload."""
        return hashlib.sha256(payload.encode()).hexdigest()

    @classmethod
    @traced(extract_args=["update"])
    async def new_or_upsert(cls, db_conn: AsyncSession, *, update: telegram.Update):
        """Insert or update a message in the database."""
        now = datetime.now(UTC)

        stmt = pg_insert(cls).values(
            update_key=cls.generate_update_key(update.to_json()),
            update_id=str(update.update_id),
            payload=update.to_dict(),
            created_at=now,
            updated_at=now,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["update_key"],
            set_={
                "payload": stmt.excluded.payload,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await db_conn.execute(stmt)
