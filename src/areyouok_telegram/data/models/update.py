"""Update Pydantic model for raw Telegram updates."""

import hashlib
from datetime import UTC, datetime

import pydantic
import telegram
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import UpdatesTable
from areyouok_telegram.logging import traced


class Update(pydantic.BaseModel):
    """Model for raw Telegram updates."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Internal ID
    id: int

    # Telegram update ID
    telegram_update_id: str

    # Update payload
    payload: dict

    # Metadata
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def generate_object_key(payload: str) -> str:
        """Generate a unique object key for an update based on its payload."""
        return hashlib.sha256(f"update:{payload}".encode()).hexdigest()

    @classmethod
    @traced(extract_args=["update"])
    async def new_or_upsert(cls, *, update: telegram.Update) -> "Update":
        """Insert or update an update in the database.

        Args:
            update: Telegram Update object

        Returns:
            Update instance
        """
        now = datetime.now(UTC)
        object_key = cls.generate_object_key(update.to_json())

        async with async_database() as db_conn:
            stmt = pg_insert(UpdatesTable).values(
                object_key=object_key,
                telegram_update_id=str(update.update_id),
                payload=update.to_dict(),
                created_at=now,
                updated_at=now,
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=["object_key"],
                set_={
                    "payload": stmt.excluded.payload,
                    "updated_at": stmt.excluded.updated_at,
                },
            ).returning(UpdatesTable)

            result = await db_conn.execute(stmt)
            row = result.scalar_one()

            return cls.model_validate(row, from_attributes=True)
