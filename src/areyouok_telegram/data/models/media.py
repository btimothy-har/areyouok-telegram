import base64
import hashlib
from datetime import UTC
from datetime import datetime

import magic
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.utils import traced


class MediaFiles(Base):
    """Store media files from messages in base64 format."""

    __tablename__ = "media_files"
    __table_args__ = {"schema": ENV}

    file_key = Column(String, nullable=False, unique=True)

    file_id = Column(String, nullable=False, index=True)
    file_unique_id = Column(String, nullable=False, index=True)

    chat_id = Column(String, nullable=False, index=True)
    message_id = Column(String, nullable=False, index=True)

    mime_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    content_base64 = Column(Text, nullable=True)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)
    last_accessed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    @staticmethod
    def generate_file_key(chat_id: str, message_id: str, file_unique_id: str) -> str:
        """Generate a unique key for a file based on its chat ID, message ID, and unique ID."""
        return hashlib.sha256(f"{chat_id}:{message_id}:{file_unique_id}".encode()).hexdigest()

    @property
    def bytes_data(self) -> bytes | None:
        """Decode base64 content back to bytes."""
        if self.content_base64:
            return base64.b64decode(self.content_base64)
        return None

    @property
    def is_anthropic_supported(self) -> bool:
        """Check if the file is supported by Anthropic.

        Anthropic supports images, PDFs, and text files.
        """
        return (
            self.mime_type.startswith("image/")
            or self.mime_type.startswith("application/pdf")
            or self.mime_type.startswith("text/")
        )

    @classmethod
    @traced(extract_args=["file_id", "chat_id", "message_id", "file_size"])
    async def create_file(
        cls,
        db_conn: AsyncSession,
        file_id: str,
        file_unique_id: str,
        chat_id: str,
        message_id: str,
        file_size: int,
        content_bytes: bytes,
    ):
        """Create a media file entry.

        Args:
            db_conn: Database connection
            file_id: Telegram file ID
            file_unique_id: Telegram unique file ID
            chat_id: Chat ID where the file was sent
            message_id: Message ID containing the file
            file_size: Size of the file in bytes
            content_bytes: Raw file content as bytes
        """
        now = datetime.now(UTC)

        # Use python-magic to get MIME type
        mime_type = magic.from_buffer(content_bytes, mime=True) if content_bytes else None

        # Create new media entry
        stmt = pg_insert(cls).values(
            file_id=file_id,
            file_unique_id=file_unique_id,
            chat_id=chat_id,
            message_id=message_id,
            mime_type=mime_type,
            file_size=file_size,
            content_base64=base64.b64encode(content_bytes).decode("ascii") if content_bytes else None,
            created_at=now,
            updated_at=now,
        )
        stmt.on_conflict_do_update(
            index_elements=["file_unique_id"],
            set_={
                "file_unique_id": stmt.excluded.file_unique_id,
                "mime_type": stmt.excluded.mime_type,
                "file_size": stmt.excluded.file_size,
                "content_base64": stmt.excluded.content_base64,
                "updated_at": datetime.now(UTC),
            },
        )

        await db_conn.execute(stmt)

    @classmethod
    @traced(extract_args=["chat_id", "message_id"])
    async def get_by_message_id(cls, db_conn: AsyncSession, chat_id: str, message_id: str) -> list["MediaFiles"]:
        """Retrieve all media files by chat_id and message_id and update last_accessed_at."""
        stmt = select(cls).where((cls.chat_id == chat_id) & (cls.message_id == message_id))
        result = await db_conn.execute(stmt)
        media_files = result.scalars().all()

        # Update last_accessed_at for all found media files
        if media_files:
            media_ids = [media.id for media in media_files]
            await cls.bulk_update_last_accessed(db_conn, media_ids)

        return media_files

    @classmethod
    @traced(extract_args=["media_ids"])
    async def bulk_update_last_accessed(cls, db_conn: AsyncSession, media_ids: list[int]) -> None:
        """Update last_accessed_at timestamp for given media IDs.

        Args:
            db_conn: Database connection
            media_ids: List of media record IDs to update
        """
        if not media_ids:
            return

        stmt = update(cls).where(cls.id.in_(media_ids)).values(last_accessed_at=datetime.now(UTC))
        await db_conn.execute(stmt)
