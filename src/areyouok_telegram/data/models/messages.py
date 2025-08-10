import hashlib
import json
from datetime import UTC
from datetime import datetime

import telegram
from cryptography.fernet import Fernet
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
    encrypted_payload = Column(String, nullable=True)

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Associate with a session key if needed
    session_key = Column(String, nullable=True)
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

    @classmethod
    def encrypt_payload(cls, payload_dict: dict, user_encryption_key: str) -> str:
        """Encrypt the payload using the user's encryption key.

        Args:
            payload_dict: The payload dictionary to encrypt
            user_encryption_key: The user's Fernet encryption key

        Returns:
            str: The encrypted payload as base64-encoded string
        """
        fernet = Fernet(user_encryption_key.encode())
        payload_json = json.dumps(payload_dict)
        encrypted_bytes = fernet.encrypt(payload_json.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt_payload(self, user_encryption_key: str) -> dict | None:
        """Decrypt the payload using the user's encryption key.

        Args:
            user_encryption_key: The user's Fernet encryption key

        Returns:
            dict: The decrypted payload dictionary, or None if no encrypted payload
        """
        if not self.encrypted_payload:
            return None

        fernet = Fernet(user_encryption_key.encode())
        encrypted_bytes = self.encrypted_payload.encode("utf-8")
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        return json.loads(decrypted_bytes.decode("utf-8"))

    def to_telegram_object(self, user_encryption_key: str) -> MessageTypes | None:
        """Convert the database record to a Telegram message object.

        Args:
            user_encryption_key: The user's encryption key for decrypting payload

        Returns:
            MessageTypes | None: The Telegram object, or None if message is deleted.
        """
        payload = self.decrypt_payload(user_encryption_key)
        if payload is None:
            return None
        return self.message_type_obj.de_json(payload, None)

    async def delete(self, db_conn: AsyncSession) -> bool:
        """Soft delete the message by clearing its encrypted payload.

        Args:
            db_conn: Database connection for persisting changes

        Returns:
            bool: True if the message was soft deleted, False if it was already deleted.
        """
        # Check if already soft deleted
        if self.encrypted_payload is None:
            return False

        # Clear the encrypted payload directly on the instance
        self.encrypted_payload = None
        db_conn.add(self)

        return True

    @classmethod
    @traced(extract_args=["user_id", "chat_id", "message"])
    async def new_or_update(
        cls,
        db_conn: AsyncSession,
        user_encryption_key: str,
        *,
        user_id: str,
        chat_id: str,
        message: MessageTypes,
        session_key: str | None = None,
    ):
        """Insert or update a message in the database with encrypted payload."""
        now = datetime.now(UTC)

        if not isinstance(message, MessageTypes):
            raise InvalidMessageTypeError(type(message).__name__)

        message_key = cls.generate_message_key(user_id, chat_id, message.message_id, message.__class__.__name__)

        # Encrypt the payload
        encrypted_payload = cls.encrypt_payload(message.to_dict(), user_encryption_key)

        stmt = pg_insert(cls).values(
            message_key=message_key,
            message_id=str(message.message_id),
            message_type=message.__class__.__name__,
            user_id=str(user_id),
            chat_id=str(chat_id),
            encrypted_payload=encrypted_payload,
            session_key=session_key,
            created_at=now,
            updated_at=now,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["message_key"],
            set_={
                "encrypted_payload": stmt.excluded.encrypted_payload,
                "updated_at": stmt.excluded.updated_at,
            },
        )

        await db_conn.execute(stmt)

    @classmethod
    @traced(extract_args=["message_id", "chat_id"])
    async def retrieve_message_by_id(
        cls,
        db_conn: AsyncSession,
        user_encryption_key: str,
        *,
        message_id: str,
        chat_id: str,
        include_reactions: bool = True,
    ) -> tuple[telegram.Message | None, list[telegram.MessageReactionUpdated] | None]:
        """Retrieve a message by its ID and chat ID, returning a telegram.Message object."""
        stmt = select(cls).where(
            cls.message_id == message_id,
            cls.chat_id == chat_id,
            cls.message_type == "Message",
            cls.encrypted_payload.isnot(None),  # Exclude soft-deleted messages
        )

        result = await db_conn.execute(stmt)
        message = result.scalar_one_or_none()

        reaction_objects: list[telegram.MessageReactionUpdated] = []

        if message and include_reactions:
            stmt = select(cls).where(
                cls.message_id == message_id,
                cls.chat_id == chat_id,
                cls.message_type == "MessageReactionUpdated",
                cls.encrypted_payload.isnot(None),  # Exclude soft-deleted reactions
            )
            reaction_result = await db_conn.execute(stmt)
            reactions = reaction_result.scalars().all()

            # Convert reactions, filtering out any that return None
            reaction_objects = []
            for r in reactions:
                obj = r.to_telegram_object(user_encryption_key)
                if obj is not None:
                    reaction_objects.append(obj)

        rt_message = message.to_telegram_object(user_encryption_key) if message else None

        return rt_message, reaction_objects if include_reactions else None

    @classmethod
    @traced(extract_args=["session_id"])
    async def retrieve_by_session(
        cls,
        db_conn: AsyncSession,
        user_encryption_key: str,
        *,
        session_id: str,
    ) -> list[MessageTypes]:
        """Retrieve messages by session_id, returning telegram.Message objects."""
        messages = await cls.retrieve_raw_by_session(db_conn, session_id)
        return [msg.to_telegram_object(user_encryption_key) for msg in messages]

    @classmethod
    @traced(extract_args=["session_id"])
    async def retrieve_raw_by_session(
        cls,
        db_conn: AsyncSession,
        session_id: str,
    ) -> list["Messages"]:
        """Retrieve messages by session_id, returning SQLAlchemy Messages models."""
        stmt = (
            select(cls)
            .where(
                cls.session_key == session_id,
                cls.encrypted_payload.isnot(None),  # Exclude soft-deleted messages
            )
            .order_by(cls.created_at)
        )

        result = await db_conn.execute(stmt)
        messages = result.scalars().all()

        return list(messages)
