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
from sqlalchemy.sql import select

from areyouok_telegram.config import ENV
from areyouok_telegram.data.connection import Base
from areyouok_telegram.data.utils import with_retry


class Users(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": ENV}

    user_id = Column(String, nullable=False, unique=True)
    is_bot = Column(BOOLEAN, nullable=False)
    language_code = Column(String, nullable=True)
    is_premium = Column(BOOLEAN, nullable=False, default=False)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @classmethod
    @with_retry()
    async def new_or_update(cls, session: AsyncSession, user: telegram.User):
        """Insert or update a user in the database."""
        now = datetime.now(UTC)

        stmt = pg_insert(cls).values(
            user_id=str(user.id),
            is_bot=user.is_bot,
            language_code=user.language_code,
            is_premium=user.is_premium if user.is_premium is not None else False,
            created_at=now,
            updated_at=now,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "is_bot": stmt.excluded.is_bot,
                "language_code": stmt.excluded.language_code,
                "is_premium": stmt.excluded.is_premium,
                "updated_at": stmt.excluded.updated_at,
            },
        )

        await session.execute(stmt)

    @classmethod
    @with_retry()
    async def get_by_id(cls, session: AsyncSession, user_id: str) -> "Users | None":
        """Retrieve a user by their ID."""
        stmt = select(cls).where(cls.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalars().first()
