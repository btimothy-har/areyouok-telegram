"""Chat Pydantic model for chat sessions with encryption keys."""

import hashlib
from datetime import UTC, datetime

import pydantic
import telegram
from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import ChatsTable
from areyouok_telegram.encryption import decrypt_chat_key, encrypt_chat_key, generate_chat_key
from areyouok_telegram.logging import traced


class Chat(pydantic.BaseModel):
    """Chat model mapping Telegram chats to internal IDs with encryption keys."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Telegram ID
    telegram_chat_id: str
    encrypted_key: str

    # Chat attributes
    type: str

    # Metadata
    id: int = 0
    title: str | None = None
    is_forum: bool = False

    created_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))

    # TTL cache for decrypted keys (10 minutes TTL, max 1000 entries)
    _key_cache: TTLCache[int, str] = TTLCache(maxsize=1000, ttl=10 * 60)

    @staticmethod
    def generate_object_key(telegram_chat_id: str) -> str:
        """Generate a unique object key for a chat based on Telegram chat ID."""
        return hashlib.sha256(f"chat:{telegram_chat_id}".encode()).hexdigest()

    @staticmethod
    def generate_encryption_key() -> str:
        """Generate a new encrypted Fernet key for a chat.

        Returns:
            Encrypted Fernet key ready to store in database
        """
        new_key = generate_chat_key()
        encrypted_key = encrypt_chat_key(new_key)
        return encrypted_key

    def retrieve_key(self) -> str | None:
        """Retrieve the chat's decrypted encryption key.

        Returns:
            str: The decrypted Fernet key, or None if no key is stored

        Raises:
            InvalidToken: If the key cannot be decrypted (corrupted data)
        """
        if not self.encrypted_key:
            return None

        # Check cache first
        if self.id in self._key_cache:
            return self._key_cache[self.id]

        # Decrypt the key and cache it
        decrypted_key = decrypt_chat_key(self.encrypted_key)
        self._key_cache[self.id] = decrypted_key
        return decrypted_key

    @classmethod
    @traced(extract_args=["id", "telegram_chat_id"])
    async def get_by_id(
        cls,
        *,
        chat_id: int | None = None,
        telegram_chat_id: str | None = None,
    ) -> "Chat | None":
        """Retrieve a chat by internal chat ID or Telegram chat ID.

        Args:
            chat_id: Internal chat ID
            telegram_chat_id: Telegram chat ID

        Returns:
            Chat instance if found, None otherwise

        Raises:
            ValueError: If neither or both IDs are provided
        """
        if sum([chat_id is not None, telegram_chat_id is not None]) != 1:
            raise ValueError("Provide exactly one of: chat_id, telegram_chat_id")

        async with async_database() as db_conn:
            if chat_id is not None:
                stmt = select(ChatsTable).where(ChatsTable.id == chat_id)
            else:
                stmt = select(ChatsTable).where(ChatsTable.telegram_chat_id == telegram_chat_id)

            result = await db_conn.execute(stmt)
            row = result.scalars().first()

            if row is None:
                return None

            return cls.model_validate(row, from_attributes=True)

    @classmethod
    def from_telegram(cls, chat: telegram.Chat) -> "Chat":
        """Create a Chat instance from a Telegram Chat object.

        Args:
            chat: Telegram Chat object

        Returns:
            Chat instance (not yet saved to database)
        """
        return cls(
            telegram_chat_id=str(chat.id),
            type=chat.type,
            title=chat.title,
            is_forum=chat.is_forum if chat.is_forum is not None else False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @traced(extract_args=False)
    async def save(self) -> "Chat":
        """Save or update the chat in the database.

        For new chats (no id set), generates encryption key and inserts.
        For existing chats, updates the record.

        Returns:
            Chat instance with updated fields from database
        """
        now = datetime.now(UTC)
        object_key = self.generate_object_key(self.telegram_chat_id)

        if not self.encrypted_key:
            self.encrypted_key = Chat.generate_encryption_key()

        async with async_database() as db_conn:
            stmt = pg_insert(ChatsTable).values(
                object_key=object_key,
                telegram_chat_id=self.telegram_chat_id,
                encrypted_key=self.encrypted_key,
                type=self.type,
                title=self.title,
                is_forum=self.is_forum,
                created_at=self.created_at,
                updated_at=now,
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=["object_key"],
                set_={
                    "type": stmt.excluded.type,
                    "title": stmt.excluded.title,
                    "is_forum": stmt.excluded.is_forum,
                    "updated_at": stmt.excluded.updated_at,
                    # Don't update encrypted_key if chat already exists
                },
            )

            await db_conn.execute(stmt)

        # Return the chat object after upsert with refreshed data from DB
        return await Chat.get_by_id(telegram_chat_id=self.telegram_chat_id)
