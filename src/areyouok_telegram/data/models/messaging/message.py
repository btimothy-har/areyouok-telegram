"""Message Pydantic model for chat messages and reactions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pydantic
import telegram
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import MessagesTable
from areyouok_telegram.data.exceptions import InvalidIDArgumentError
from areyouok_telegram.data.models.messaging.chat import Chat
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import db_retry

MessageTypes = telegram.Message | telegram.MessageReactionUpdated


class InvalidMessageTypeError(Exception):
    def __init__(self, message_type: str):
        super().__init__(f"Invalid message type: {message_type}. Expected 'Message' or 'MessageReactionUpdated'.")
        self.message_type = message_type


class Message(pydantic.BaseModel):
    """Message model for chat messages and reactions."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Required fields
    chat: Chat
    user_id: int
    telegram_message_id: int
    message_type: str
    payload: dict

    # Optional fields
    id: int = 0
    session_id: int | None = None
    reasoning: str | None = None
    created_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))

    @property
    def object_key(self) -> str:
        """Generate a unique object key for a message using internal IDs."""
        return hashlib.sha256(
            f"message:{self.user_id}:{self.chat.id}:{self.telegram_message_id}:{self.message_type}".encode()
        ).hexdigest()

    @staticmethod
    def decrypt_message(
        encrypted_payload: str, encrypted_reasoning: str | None, user_encryption_key: str
    ) -> tuple[dict, str | None]:
        """Decrypt both message payload and reasoning together.

        Args:
            encrypted_payload: The encrypted payload string
            encrypted_reasoning: The encrypted reasoning string (or None)
            user_encryption_key: The user's Fernet encryption key

        Returns:
            Tuple of (decrypted_payload_dict, decrypted_reasoning_str_or_none)
        """
        fernet = Fernet(user_encryption_key.encode())

        # Decrypt payload
        encrypted_bytes = encrypted_payload.encode("utf-8")
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        payload_dict = json.loads(decrypted_bytes.decode("utf-8"))

        # Decrypt reasoning if present
        decrypted_reasoning = None
        if encrypted_reasoning:
            encrypted_bytes = encrypted_reasoning.encode("utf-8")
            decrypted_bytes = fernet.decrypt(encrypted_bytes)
            decrypted_reasoning = decrypted_bytes.decode("utf-8")

        return payload_dict, decrypted_reasoning

    def encrypt_message(self) -> tuple[str, str | None]:
        """Encrypt both message payload and reasoning together using chat's encryption key.

        Returns:
            Tuple of (encrypted_payload_str, encrypted_reasoning_str_or_none)
        """
        user_encryption_key = self.chat.retrieve_key()
        fernet = Fernet(user_encryption_key.encode())

        # Encrypt payload
        payload_json = json.dumps(self.payload)
        encrypted_bytes = fernet.encrypt(payload_json.encode("utf-8"))
        encrypted_payload = encrypted_bytes.decode("utf-8")

        # Encrypt reasoning if present
        encrypted_reasoning = None
        if self.reasoning:
            encrypted_bytes = fernet.encrypt(self.reasoning.encode("utf-8"))
            encrypted_reasoning = encrypted_bytes.decode("utf-8")

        return encrypted_payload, encrypted_reasoning

    @property
    def chat_id(self) -> int:
        """Get chat_id from the Chat object."""
        return self.chat.id

    @property
    def message_type_obj(self) -> type[MessageTypes]:
        """Return the class type of the message based on its type string."""
        if self.message_type == "MessageReactionUpdated":
            return telegram.MessageReactionUpdated
        elif self.message_type == "Message":
            return telegram.Message
        else:
            raise InvalidMessageTypeError(self.message_type)

    @property
    def telegram_object(self) -> MessageTypes:
        """Convert the payload to a Telegram message object.

        Returns:
            MessageTypes: The Telegram object
        """
        return self.message_type_obj.de_json(self.payload, None)

    @traced(extract_args=False)
    @db_retry()
    async def save(self) -> Message:
        """Save or update the message in the database with encrypted payload.

        Returns:
            Message instance refreshed from database
        """
        now = datetime.now(UTC)

        # Encrypt the payload and reasoning together
        encrypted_payload, encrypted_reasoning = self.encrypt_message()

        async with async_database() as db_conn:
            stmt = pg_insert(MessagesTable).values(
                object_key=self.object_key,
                user_id=self.user_id,
                chat_id=self.chat.id,
                telegram_message_id=self.telegram_message_id,
                message_type=self.message_type,
                encrypted_payload=encrypted_payload,
                encrypted_reasoning=encrypted_reasoning,
                session_id=self.session_id,
                created_at=self.created_at,
                updated_at=now,
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=["object_key"],
                set_={
                    "encrypted_payload": stmt.excluded.encrypted_payload,
                    "encrypted_reasoning": stmt.excluded.encrypted_reasoning,
                    "updated_at": stmt.excluded.updated_at,
                },
            )

            # Return the ID of the inserted/updated row
            stmt = stmt.returning(MessagesTable.id)
            result = await db_conn.execute(stmt)
            message_id = result.scalar_one()

        # Return refreshed from database using the internal ID
        return await Message.get_by_id(
            self.chat,
            message_id=message_id,
        )

    @classmethod
    def from_telegram(
        cls,
        *,
        user_id: int,
        chat: Chat,
        message: MessageTypes,
        session_id: int | None = None,
        reasoning: str | None = None,
    ) -> Message:
        """Create a Message instance from a Telegram message object.

        Args:
            user_id: Internal user ID (FK to users.id)
            chat: Chat object
            message: Telegram message object
            session_id: Optional internal session ID (FK to sessions.id)
            reasoning: Optional AI reasoning for bot messages

        Returns:
            Message instance (not yet saved to database)
        """
        return cls(
            user_id=user_id,
            chat=chat,
            telegram_message_id=message.message_id,
            message_type=message.__class__.__name__,
            payload=message.to_dict(),
            reasoning=reasoning,
            session_id=session_id,
        )

    @classmethod
    @traced(extract_args=False)
    @db_retry()
    async def get_by_id(
        cls,
        chat: Chat,
        *,
        message_id: int | None = None,
        telegram_message_id: int | None = None,
    ) -> Message | None:
        """Retrieve a message by internal ID or Telegram message ID, auto-decrypted.

        Args:
            chat: Chat object (provides chat_id and encryption key)
            message_id: Internal message ID
            telegram_message_id: Telegram message ID

        Returns:
            Decrypted Message instance if found, None otherwise

        Raises:
            ValueError: If neither or both IDs are provided
        """
        if sum([message_id is not None, telegram_message_id is not None]) != 1:
            raise InvalidIDArgumentError(["message_id", "telegram_message_id"])

        async with async_database() as db_conn:
            if message_id is not None:
                stmt = select(MessagesTable).where(MessagesTable.id == message_id)
            else:
                stmt = select(MessagesTable).where(
                    MessagesTable.telegram_message_id == telegram_message_id,
                    MessagesTable.chat_id == chat.id,
                    MessagesTable.message_type == "Message",
                )

            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return None

            # Decrypt payload and reasoning together
            encryption_key = chat.retrieve_key()
            decrypted_payload, decrypted_reasoning = cls.decrypt_message(
                row.encrypted_payload, row.encrypted_reasoning, encryption_key
            )

            return Message(
                id=row.id,
                user_id=row.user_id,
                chat=chat,
                session_id=row.session_id,
                telegram_message_id=row.telegram_message_id,
                message_type=row.message_type,
                payload=decrypted_payload,
                reasoning=decrypted_reasoning,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    @classmethod
    @traced(extract_args=["session_id"])
    @db_retry()
    async def get_by_session(
        cls,
        chat: Chat,
        *,
        session_id: int,
    ) -> list[Message]:
        """Retrieve messages by session_id, auto-decrypted.

        Args:
            chat: Chat object (provides encryption key and chat context)
            session_id: Internal session ID (FK to sessions.id)

        Returns:
            List of decrypted Message instances
        """
        async with async_database() as db_conn:
            stmt = (
                select(MessagesTable)
                .where(MessagesTable.session_id == session_id)
                .where(MessagesTable.chat_id == chat.id)
                .order_by(MessagesTable.created_at)
            )

            result = await db_conn.execute(stmt)
            rows = result.scalars().all()

            # Decrypt messages
            encryption_key = chat.retrieve_key()
            messages = []

            for row in rows:
                # Decrypt payload and reasoning together
                decrypted_payload, decrypted_reasoning = cls.decrypt_message(
                    row.encrypted_payload, row.encrypted_reasoning, encryption_key
                )

                message = Message(
                    id=row.id,
                    user_id=row.user_id,
                    chat=chat,
                    session_id=row.session_id,
                    telegram_message_id=row.telegram_message_id,
                    message_type=row.message_type,
                    payload=decrypted_payload,
                    reasoning=decrypted_reasoning,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                messages.append(message)

            return messages
