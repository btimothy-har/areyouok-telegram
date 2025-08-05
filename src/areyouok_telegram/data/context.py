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
from areyouok_telegram.data.connection import Base
from areyouok_telegram.data.utils import with_retry

VALID_CONTEXT_TYPES = [
    "session",
]


class InvalidContextTypeError(Exception):
    def __init__(self, context_type: str):
        super().__init__(f"Invalid context type: {context_type}. Expected one of: {VALID_CONTEXT_TYPES}.")
        self.context_type = context_type


class Context(Base):
    __tablename__ = "context"
    __table_args__ = {"schema": ENV}

    chat_id = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    type = Column(String, nullable=False)
    content = Column(String, nullable=False)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @classmethod
    @with_retry()
    async def new_or_update(
        cls,
        db_conn: AsyncSession,
        chat_id: str,
        session_id: str,
        ctype: str,
        content: str,
    ):
        """Insert or update a context item in the database."""
        now = datetime.now(UTC)

        if ctype not in VALID_CONTEXT_TYPES:
            raise InvalidContextTypeError(ctype)

        stmt = pg_insert(cls).values(
            chat_id=str(chat_id),
            session_id=session_id,
            type=ctype,
            content=content,
            created_at=now,
        )

        await db_conn.execute(stmt)

    @classmethod
    @with_retry()
    async def get_by_session_id(
        cls,
        db_conn: AsyncSession,
        session_id: str,
        ctype: str | None = None,
    ) -> list["Context"] | None:
        """Retrieve a context by session_id, optionally filtered by type."""

        if ctype and ctype not in VALID_CONTEXT_TYPES:
            raise InvalidContextTypeError(ctype)

        stmt = select(cls).where(cls.session_id == session_id)

        if ctype:
            stmt = stmt.where(cls.type == ctype)

        result = await db_conn.execute(stmt)
        contexts = result.scalars().all()

        return contexts if contexts else None

    @classmethod
    @with_retry()
    async def get_by_chat_id(
        cls,
        db_conn: AsyncSession,
        chat_id: str,
        ctype: str | None = None,
    ) -> list["Context"] | None:
        """Retrieve a context by chat_id, optionally filtered by type."""

        if ctype and ctype not in VALID_CONTEXT_TYPES:
            raise InvalidContextTypeError(ctype)

        stmt = select(cls).where(cls.chat_id == chat_id)

        if ctype:
            stmt = stmt.where(cls.type == ctype)

        result = await db_conn.execute(stmt)
        contexts = result.scalars().all()

        return contexts if contexts else None

    @classmethod
    @with_retry()
    async def retrieve_context_by_chat(
        cls,
        db_conn: AsyncSession,
        chat_id: str,
        ctype: str | None = None,
        limit: int = 3,
    ) -> list["Context"] | None:
        """Retrieve contexts by chat_id and optional type, returning a list of Context objects."""

        if ctype and ctype not in VALID_CONTEXT_TYPES:
            raise InvalidContextTypeError(ctype)

        stmt = select(cls).where(cls.chat_id == chat_id)

        if ctype:
            stmt = stmt.where(cls.type == ctype)

        stmt = stmt.order_by(cls.created_at.desc()).limit(limit)

        result = await db_conn.execute(stmt)
        contexts = result.scalars().all()

        return contexts if contexts else None
