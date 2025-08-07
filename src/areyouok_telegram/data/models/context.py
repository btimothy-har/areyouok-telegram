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

    context_key = Column(String, nullable=False, unique=True)

    chat_id = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    type = Column(String, nullable=False)
    content = Column(String, nullable=False)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_context_key(chat_id: str, ctype: str, content: str) -> str:
        """Generate a unique key for a context based on chat ID, type, content, and message type."""
        return hashlib.sha256(f"{chat_id}:{ctype}:{content}".encode()).hexdigest()

    @classmethod
    @traced(extract_args=["chat_id", "session_id", "ctype"])
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
            context_key=cls.generate_context_key(chat_id, ctype, content),
            chat_id=str(chat_id),
            session_id=session_id,
            type=ctype,
            content=content,
            created_at=now,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["context_key"],
            set_={
                "session_id": stmt.excluded.session_id,
                "content": stmt.excluded.content,
                "created_at": stmt.excluded.created_at,
            },
        )

        await db_conn.execute(stmt)

    @classmethod
    @traced(extract_args=["session_id"])
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
    @traced(extract_args=["chat_id"])
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
    @traced(extract_args=["chat_id"])
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
