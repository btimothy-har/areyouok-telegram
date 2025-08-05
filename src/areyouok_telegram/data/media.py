import base64
from datetime import UTC
from datetime import datetime
from typing import Optional

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
from areyouok_telegram.data.connection import Base
from areyouok_telegram.data.utils import with_retry


class MediaFiles(Base):
    """Store media files from messages in base64 format."""

    __tablename__ = "media_files"
    __table_args__ = {"schema": ENV}

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Telegram identifiers
    file_id = Column(String, nullable=False, index=True)
    file_unique_id = Column(String, nullable=False, index=True)

    chat_id = Column(String, nullable=False, index=True)
    message_id = Column(String, nullable=False, index=True)

    # Media type using MIME type standard
    mime_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)

    # Content storage in base64
    content_base64 = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)
    last_accessed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    @property
    def bytes_data(self) -> bytes | None:
        """Decode base64 content back to bytes."""
        if self.content_base64:
            return base64.b64decode(self.content_base64)
        return None

    @classmethod
    @with_retry()
    async def get_by_file_id(cls, session: AsyncSession, file_id: str) -> Optional["MediaFiles"]:
        """Retrieve media by file_id and update last_accessed_at."""
        stmt = select(cls).where(cls.file_id == file_id)
        result = await session.execute(stmt)
        media = result.scalar_one_or_none()

        # Update last_accessed_at if media was found
        if media:
            await cls.update_last_accessed(session, [media.id])

        return media

    @classmethod
    @with_retry()
    async def get_by_message_id(cls, session: AsyncSession, chat_id: str, message_id: str) -> list["MediaFiles"]:
        """Retrieve all media files by chat_id and message_id and update last_accessed_at."""
        stmt = select(cls).where((cls.chat_id == chat_id) & (cls.message_id == message_id))
        result = await session.execute(stmt)
        media_files = result.scalars().all()

        # Update last_accessed_at for all found media files
        if media_files:
            media_ids = [media.id for media in media_files]
            await cls.update_last_accessed(session, media_ids)

        return media_files

    @classmethod
    @with_retry()
    async def get_agent_compatible_media(
        cls, session: AsyncSession, chat_id: str, message_id: str
    ) -> list["MediaFiles"]:
        """Retrieve media files that are compatible with the agent (images and PDFs only).

        Args:
            session: Database session
            chat_id: Chat ID
            message_id: Message ID

        Returns:
            List of media files that can be processed by the agent
        """
        # Get all media for the message
        all_media = await cls.get_by_message_id(session, chat_id, message_id)

        # Filter to only include images and PDFs that Anthropic can process
        return [
            media
            for media in all_media
            if media.mime_type and (media.mime_type.startswith("image/") or media.mime_type == "application/pdf")
        ]

    @classmethod
    @with_retry()
    async def create_file(
        cls,
        session: AsyncSession,
        file_id: str,
        file_unique_id: str,
        chat_id: str,
        message_id: str,
        file_size: int | None,
        content_bytes: bytes,
    ):
        """Create a media file entry.

        Args:
            session: Database session
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

        await session.execute(stmt)

    @classmethod
    @with_retry()
    async def update_last_accessed(cls, session: AsyncSession, media_ids: list[int]) -> None:
        """Update last_accessed_at timestamp for given media IDs.

        Args:
            session: Database session
            media_ids: List of media record IDs to update
        """
        if not media_ids:
            return

        stmt = update(cls).where(cls.id.in_(media_ids)).values(last_accessed_at=datetime.now(UTC))
        await session.execute(stmt)
