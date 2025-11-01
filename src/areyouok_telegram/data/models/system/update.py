"""Update Pydantic model for raw Telegram updates."""

import hashlib
import json
from datetime import UTC, datetime

import pydantic
import telegram
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import UpdatesTable
from areyouok_telegram.utils.retry import db_retry


class Update(pydantic.BaseModel):
    """Model for raw Telegram updates."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    telegram_update_id: int
    payload: dict

    # Metadata
    id: int = 0
    created_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))

    @property
    def object_key(self) -> str:
        """Generate a unique object key for an update based on its payload."""

        payload_str = json.dumps(self.payload, sort_keys=True)
        return hashlib.sha256(f"update:{payload_str}".encode()).hexdigest()

    @classmethod
    def from_telegram(cls, *, update: telegram.Update) -> "Update":
        """Create an Update instance from a Telegram Update object.

        Args:
            update: Telegram Update object

        Returns:
            Update instance (not yet saved to database)
        """
        return cls(
            telegram_update_id=update.update_id,
            payload=update.to_dict(),
        )

    @db_retry()
    async def save(self) -> "Update":
        """Save or update the update in the database.

        Returns:
            Update instance refreshed from database
        """
        now = datetime.now(UTC)

        async with async_database() as db_conn:
            stmt = pg_insert(UpdatesTable).values(
                object_key=self.object_key,
                telegram_update_id=self.telegram_update_id,
                payload=self.payload,
                created_at=self.created_at,
                updated_at=now,
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=["object_key"],
                set_={
                    "payload": stmt.excluded.payload,
                    "updated_at": stmt.excluded.updated_at,
                },
            ).returning(UpdatesTable.id)

            result = await db_conn.execute(stmt)
            row_id = result.scalar_one()

        # Return refreshed from database using get_by_id
        return await Update.get_by_id(update_id=row_id)

    @classmethod
    @db_retry()
    async def get_by_id(cls, *, update_id: int) -> "Update | None":
        """Retrieve an update by its internal ID.

        Args:
            update_id: Internal update ID

        Returns:
            Update instance if found, None otherwise
        """
        async with async_database() as db_conn:
            stmt = select(UpdatesTable).where(UpdatesTable.id == update_id)
            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return None

            return Update.model_validate(row, from_attributes=True)
