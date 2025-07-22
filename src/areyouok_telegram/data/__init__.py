from datetime import UTC
from datetime import datetime

import telegram
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.data.connection import Base
from areyouok_telegram.data.connection import async_database_session
from areyouok_telegram.data.connection import async_engine
from areyouok_telegram.data.messages import Messages
from areyouok_telegram.data.updates import Updates
from areyouok_telegram.data.utils import with_retry


@with_retry()
async def new_or_upsert_message(session: AsyncSession, user_id: str, chat_id: str, message: telegram.Message):
    """Insert or update a message in the database."""
    now = datetime.now(UTC)

    message_key = Messages.generate_message_key(user_id, chat_id, message.message_id)

    stmt = pg_insert(Messages).values(
        message_key=message_key,
        message_id=str(message.message_id),
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
    await session.commit()


@with_retry()
async def new_or_upsert_update(session: AsyncSession, update: telegram.Update):
    """Insert a raw update payload. Used for logging and debugging."""
    now = datetime.now(UTC)

    stmt = pg_insert(Updates).values(
        update_key=Updates.generate_update_key(update.to_json()),
        update_id=str(update.update_id),
        payload=update.to_dict(),
        created_at=now,
        updated_at=now,
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=["update_key"],
        set_={
            "payload": stmt.excluded.payload,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)
    await session.commit()


__all__ = [
    "async_database_session",
    "async_engine",
    "Base",
    "new_or_upsert_message",
    "new_or_upsert_update",
]
