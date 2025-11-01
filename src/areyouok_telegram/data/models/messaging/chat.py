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
from areyouok_telegram.data.exceptions import MissingEncryptionKeyError
from areyouok_telegram.encryption import decrypt_chat_key, encrypt_chat_key, generate_chat_key
from areyouok_telegram.utils.retry import db_retry


class Chat(pydantic.BaseModel):
    """Chat model mapping Telegram chats to internal IDs with encryption keys."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Telegram ID
    telegram_chat_id: int

    # Chat attributes
    type: str

    # Metadata
    id: int = 0
    title: str | None = None
    is_forum: bool = False
    encrypted_key: str | None = None

    created_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))

    # TTL cache for decrypted keys (10 minutes TTL, max 1000 entries)
    _key_cache: TTLCache[int, str] = TTLCache(maxsize=1000, ttl=10 * 60)

    @pydantic.model_validator(mode="after")
    def validate_encrypted_key(self) -> "Chat":
        """Validate that saved chats have an encrypted key."""
        if self.id != 0 and not self.encrypted_key:
            raise MissingEncryptionKeyError(self.id)
        return self

    @property
    def object_key(self) -> str:
        """Generate a unique object key for a chat based on Telegram chat ID."""
        return hashlib.sha256(f"chat:{self.telegram_chat_id}".encode()).hexdigest()

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
    @db_retry()
    async def get_by_id(cls, *, chat_id: int) -> "Chat | None":
        """Retrieve a chat by internal chat ID.

        Args:
            chat_id: Internal chat ID

        Returns:
            Chat instance if found, None otherwise
        """
        async with async_database() as db_conn:
            stmt = select(ChatsTable).where(ChatsTable.id == chat_id)
            result = await db_conn.execute(stmt)
            row = result.scalars().first()

            if row is None:
                return None

            return cls.model_validate(row, from_attributes=True)

    @classmethod
    @db_retry()
    async def get_by_telegram_id(cls, *, telegram_chat_id: int) -> "Chat | None":
        """Retrieve a chat by Telegram chat ID.

        Args:
            telegram_chat_id: Telegram chat ID

        Returns:
            Chat instance if found, None otherwise
        """
        # Query for ID only
        async with async_database() as db_conn:
            stmt = select(ChatsTable.id).where(ChatsTable.telegram_chat_id == telegram_chat_id)
            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return None

        # Hydrate via get_by_id
        return await cls.get_by_id(chat_id=row)

    @classmethod
    @db_retry()
    async def get(
        cls,
        *,
        chat_type: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> list["Chat"]:
        """Retrieve chats with optional filtering.

        Args:
            chat_type: Optional chat type to filter by (e.g., "private", "group")
            from_timestamp: Optional start of time range (created_at >= this)
            to_timestamp: Optional end of time range (created_at < this)
            limit: Optional maximum number of results

        Returns:
            List of Chat instances matching the criteria
        """
        async with async_database() as db_conn:
            stmt = select(ChatsTable)

            if chat_type:
                stmt = stmt.where(ChatsTable.type == chat_type)

            if from_timestamp:
                stmt = stmt.where(ChatsTable.created_at >= from_timestamp)

            if to_timestamp:
                stmt = stmt.where(ChatsTable.created_at < to_timestamp)

            stmt = stmt.order_by(ChatsTable.created_at.desc())

            if limit:
                stmt = stmt.limit(limit)

            result = await db_conn.execute(stmt)
            rows = result.scalars().all()
            return [cls.model_validate(row, from_attributes=True) for row in rows]

    @classmethod
    def from_telegram(cls, chat: telegram.Chat) -> "Chat":
        """Create a Chat instance from a Telegram Chat object.

        Args:
            chat: Telegram Chat object

        Returns:
            Chat instance (not yet saved to database)
        """
        return cls(
            telegram_chat_id=chat.id,
            type=chat.type,
            title=chat.title,
            is_forum=chat.is_forum if chat.is_forum is not None else False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @db_retry()
    async def save(self) -> "Chat":
        """Save or update the chat in the database.

        For new chats (no id set), generates encryption key and inserts.
        For existing chats, updates the record.

        Returns:
            Chat instance with updated fields from database
        """
        now = datetime.now(UTC)

        if not self.encrypted_key:
            self.encrypted_key = Chat.generate_encryption_key()

        async with async_database() as db_conn:
            stmt = pg_insert(ChatsTable).values(
                object_key=self.object_key,
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
            ).returning(ChatsTable.id)

            result = await db_conn.execute(stmt)
            row_id = result.scalar_one()

        # Return via get_by_id for consistent hydration
        return await Chat.get_by_id(chat_id=row_id)
