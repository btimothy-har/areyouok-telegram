import hashlib
from datetime import UTC
from datetime import datetime

import telegram
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data.connection import Base
from areyouok_telegram.data.utils import with_retry

MessageTypes = telegram.Message | telegram.MessageReactionUpdated


class InvalidMessageTypeError(Exception):
    def __init__(self, message_type: str):
        super().__init__(f"Invalid message type: {message_type}. Expected 'Message' or 'MessageReactionUpdated'.")
        self.message_type = message_type


class Messages(Base):
    __tablename__ = "messages"
    __table_args__ = {"schema": ENV}

    message_key = Column(String, nullable=False, unique=True)
    message_id = Column(String, nullable=False)
    message_type = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    chat_id = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_message_key(user_id: str, chat_id: str, message_id: int, message_type: str) -> str:
        """Generate a unique key for a message based on user ID, chat ID, message ID, and message type."""
        return hashlib.sha256(f"{user_id}:{chat_id}:{message_id}:{message_type}".encode()).hexdigest()

    @property
    def message_type_obj(self) -> type[MessageTypes]:
        """Return the class type of the message based on its type string."""
        if self.message_type == "MessageReactionUpdated":
            return telegram.MessageReactionUpdated
        elif self.message_type == "Message":
            return telegram.Message
        else:
            raise InvalidMessageTypeError(self.message_type)

    def to_telegram_object(self) -> MessageTypes:
        """Convert the database record to a Telegram message object."""
        return self.message_type_obj.de_json(self.payload, None)

    @classmethod
    @with_retry()
    async def new_or_update(
        cls,
        session: AsyncSession,
        user_id: str,
        chat_id: str,
        message: MessageTypes,
    ):
        """Insert or update a message in the database."""
        now = datetime.now(UTC)

        if not isinstance(message, (telegram.Message, telegram.MessageReactionUpdated)):
            raise InvalidMessageTypeError(type(message).__name__)

        message_key = cls.generate_message_key(user_id, chat_id, message.message_id, message.__class__.__name__)

        stmt = pg_insert(cls).values(
            message_key=message_key,
            message_id=str(message.message_id),
            message_type=message.__class__.__name__,
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

    @classmethod
    @with_retry()
    async def retrieve_message_by_id(
        cls,
        session: AsyncSession,
        message_id: str,
        chat_id: str,
    ) -> tuple[telegram.Message | None, list[telegram.MessageReactionUpdated] | None]:
        """Retrieve a message by its ID and chat ID, returning a telegram.Message object."""
        stmt = select(cls).where(
            cls.message_id == message_id,
            cls.chat_id == chat_id,
            cls.message_type == "Message",
        )

        result = await session.execute(stmt)
        message = result.scalar_one_or_none()

        if message:
            stmt = select(cls).where(
                cls.message_id == message_id,
                cls.chat_id == chat_id,
                cls.message_type == "MessageReactionUpdated",
            )
            reaction_result = await session.execute(stmt)
            reactions = reaction_result.scalars().all()

            return message.to_telegram_object(), [r.to_telegram_object() for r in reactions]

        return None, None

    @classmethod
    @with_retry()
    async def retrieve_by_chat(
        cls,
        session: AsyncSession,
        chat_id: str,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[MessageTypes]:
        """Retrieve messages by chat_id and optional time range, returning telegram.Message objects."""
        stmt = select(cls).where(cls.chat_id == chat_id)

        if from_time:
            stmt = stmt.where(cls.created_at >= from_time)

        if to_time:
            stmt = stmt.where(cls.created_at <= to_time)

        stmt = stmt.order_by(cls.created_at)

        if limit:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        messages = result.scalars().all()

        return [msg.to_telegram_object() for msg in messages]
