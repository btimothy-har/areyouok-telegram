import hashlib
from datetime import UTC
from datetime import datetime
from typing import Optional

import telegram
from cachetools import TTLCache
from sqlalchemy import BOOLEAN
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.encryption import decrypt_user_key
from areyouok_telegram.encryption import encrypt_user_key
from areyouok_telegram.encryption import generate_user_key
from areyouok_telegram.encryption.exceptions import ProfileNotDecryptedError
from areyouok_telegram.utils import traced


class Users(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": ENV}

    user_key = Column(String, nullable=False, unique=True)
    encrypted_key = Column(String, nullable=True)

    user_id = Column(String, nullable=False)
    is_bot = Column(BOOLEAN, nullable=False)
    language_code = Column(String, nullable=True)
    is_premium = Column(BOOLEAN, nullable=False, default=False)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    # TTL cache for decrypted keys (2 hours TTL, max 1000 entries)
    _key_cache: TTLCache[str, str] = TTLCache(maxsize=1000, ttl=7200)

    @staticmethod
    def generate_user_key(user_id: str) -> str:
        """Generate a unique key for a user based on their user ID."""
        return hashlib.sha256(f"{user_id}".encode()).hexdigest()

    @classmethod
    @traced(extract_args=["user"])
    async def new_or_update(cls, db_conn: AsyncSession, user: telegram.User) -> "Users":
        """Insert or update a user in the database and return the User object."""
        now = datetime.now(UTC)

        # Check if user already exists
        existing_user = await cls.get_by_id(db_conn, str(user.id))

        # Generate and encrypt key only for new users with username
        encrypted_key = None
        if not existing_user and user.username:
            # Generate a new Fernet key for the user
            new_key = generate_user_key()
            # Encrypt it using their username
            encrypted_key = encrypt_user_key(new_key, user.username)

        stmt = pg_insert(cls).values(
            user_key=cls.generate_user_key(str(user.id)),
            encrypted_key=encrypted_key,
            user_id=str(user.id),
            is_bot=user.is_bot,
            language_code=user.language_code,
            is_premium=user.is_premium if user.is_premium is not None else False,
            created_at=now,
            updated_at=now,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["user_key"],
            set_={
                "is_bot": stmt.excluded.is_bot,
                "language_code": stmt.excluded.language_code,
                "is_premium": stmt.excluded.is_premium,
                "updated_at": stmt.excluded.updated_at,
                # Don't update encrypted_key if user already exists
            },
        )

        await db_conn.execute(stmt)

        # Return the user object after upsert
        return await cls.get_by_id(db_conn, str(user.id))

    @classmethod
    @traced(extract_args=["user_id"])
    async def get_by_id(cls, db_conn: AsyncSession, user_id: str) -> Optional["Users"]:
        """Retrieve a user by their ID."""
        stmt = select(cls).where(cls.user_id == user_id)
        result = await db_conn.execute(stmt)
        return result.scalars().first()

    def retrieve_key(self, username: str | None = None) -> str | None:
        """Retrieve the user's encryption key, optionally decrypting it.

        Args:
            username: The username to use for decryption. If None, will not attempt decryption.

        Returns:
            str: The decrypted Fernet key, or None if no key is stored

        Raises:
            InvalidToken: If the key cannot be decrypted (wrong username or corrupted data)
            ProfileNotDecryptedError: If username is None and key is not in cache
        """
        if not self.encrypted_key:
            return None

        if username:
            # Username provided: attempt to decrypt and extend cache
            # Check cache first
            if self.user_key in self._key_cache:
                return self._key_cache[self.user_key]

            # Decrypt the key and cache it
            decrypted_key = decrypt_user_key(self.encrypted_key, username)
            self._key_cache[self.user_key] = decrypted_key
            return decrypted_key
        else:
            # Username not provided: return from cache or raise error
            if self.user_key in self._key_cache:
                return self._key_cache[self.user_key]
            else:
                raise ProfileNotDecryptedError(self.user_id)
