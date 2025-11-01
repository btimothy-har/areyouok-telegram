"""User Pydantic model for user accounts and profiles."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pydantic
import telegram
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import UsersTable
from areyouok_telegram.data.exceptions import InvalidIDArgumentError
from areyouok_telegram.utils.retry import db_retry


class User(pydantic.BaseModel):
    """User account model mapping Telegram users to internal IDs."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Required fields
    telegram_user_id: int
    is_bot: bool

    # Optional fields
    id: int = 0
    language_code: str | None = None
    is_premium: bool = False
    created_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))

    @property
    def object_key(self) -> str:
        """Generate a unique object key for a user based on their Telegram user ID."""
        return hashlib.sha256(f"user:{self.telegram_user_id}".encode()).hexdigest()

    @classmethod
    @db_retry()
    async def get_by_id(
        cls,
        *,
        user_id: int | None = None,
        telegram_user_id: int | None = None,
    ) -> User | None:
        """Retrieve a user by internal ID or Telegram user ID.

        Args:
            user_id: Internal user ID
            telegram_user_id: Telegram user ID

        Returns:
            User instance if found, None otherwise

        Raises:
            ValueError: If neither or both IDs are provided
        """
        if sum([user_id is not None, telegram_user_id is not None]) != 1:
            raise InvalidIDArgumentError(["user_id", "telegram_user_id"])

        async with async_database() as db_conn:
            if user_id is not None:
                stmt = select(UsersTable).where(UsersTable.id == user_id)
            else:
                stmt = select(UsersTable).where(UsersTable.telegram_user_id == telegram_user_id)

            result = await db_conn.execute(stmt)
            row = result.scalars().first()

            if row is None:
                return None

            return cls.model_validate(row, from_attributes=True)

    @db_retry()
    async def save(self) -> User:
        """Save or update the user in the database.

        Returns:
            User instance refreshed from database
        """
        now = datetime.now(UTC)

        async with async_database() as db_conn:
            stmt = pg_insert(UsersTable).values(
                object_key=self.object_key,
                telegram_user_id=self.telegram_user_id,
                is_bot=self.is_bot,
                language_code=self.language_code,
                is_premium=self.is_premium,
                created_at=self.created_at,
                updated_at=now,
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=["object_key"],
                set_={
                    "is_bot": stmt.excluded.is_bot,
                    "language_code": stmt.excluded.language_code,
                    "is_premium": stmt.excluded.is_premium,
                    "updated_at": stmt.excluded.updated_at,
                },
            )

            await db_conn.execute(stmt)

        # Return the user object after upsert
        return await User.get_by_id(telegram_user_id=self.telegram_user_id)

    @classmethod
    def from_telegram(cls, user: telegram.User) -> User:
        """Create a User instance from a Telegram User object.

        Args:
            user: Telegram User object

        Returns:
            User instance (not yet saved to database)
        """
        return cls(
            telegram_user_id=user.id,
            is_bot=user.is_bot,
            language_code=user.language_code,
            is_premium=user.is_premium if user.is_premium is not None else False,
        )
