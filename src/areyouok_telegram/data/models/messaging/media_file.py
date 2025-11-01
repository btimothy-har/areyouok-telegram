"""MediaFile Pydantic model for uploaded media content."""

from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import UTC, datetime

import pydantic
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import MediaFilesTable
from areyouok_telegram.data.models.messaging.chat import Chat
from areyouok_telegram.utils.retry import db_retry


class MediaFile(pydantic.BaseModel):
    """Media file model for uploaded media content."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Required fields
    chat: Chat
    message_id: int
    file_id: str
    file_unique_id: str
    mime_type: str
    bytes_data: bytes

    # Optional fields
    id: int = 0
    file_size: int | None = None
    created_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))

    @property
    def chat_id(self) -> int:
        """Get chat_id from the Chat object."""
        return self.chat.id

    @property
    def object_key(self) -> str:
        """Generate a unique object key using internal IDs."""
        return hashlib.sha256(f"media:{self.chat.id}:{self.message_id}:{self.file_unique_id}".encode()).hexdigest()

    @staticmethod
    def decrypt_content(encrypted_content_base64: str, chat_encryption_key: str) -> bytes:
        """Decrypt the byte content using the chat's encryption key.

        Args:
            encrypted_content_base64: The encrypted content as base64 string
            chat_encryption_key: The chat's Fernet encryption key

        Returns:
            bytes: The decrypted file content as bytes
        """
        fernet = Fernet(chat_encryption_key.encode())
        encrypted_bytes = base64.b64decode(encrypted_content_base64.encode("ascii"))
        return fernet.decrypt(encrypted_bytes)

    def encrypt_content(self) -> str:
        """Encrypt the byte content using the chat's encryption key.

        Returns:
            str: The encrypted content as base64-encoded string for storage
        """
        chat_encryption_key = self.chat.retrieve_key()
        fernet = Fernet(chat_encryption_key.encode())
        encrypted_bytes = fernet.encrypt(self.bytes_data)
        return base64.b64encode(encrypted_bytes).decode("ascii")

    @classmethod
    @db_retry()
    async def get_by_id(cls, chat: Chat, *, media_file_id: int) -> MediaFile | None:
        """Retrieve a media file by its internal ID, auto-decrypted.

        Args:
            chat: Chat object (provides encryption key)
            media_file_id: Internal media file ID

        Returns:
            Decrypted MediaFile instance if found, None otherwise
        """
        async with async_database() as db_conn:
            stmt = select(MediaFilesTable).where(MediaFilesTable.id == media_file_id)
            result = await db_conn.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return None

            encryption_key = chat.retrieve_key()
            decrypted_bytes = cls.decrypt_content(row.encrypted_content_base64, encryption_key)

            return MediaFile(
                id=row.id,
                chat=chat,
                message_id=row.message_id,
                file_id=row.file_id,
                file_unique_id=row.file_unique_id,
                mime_type=row.mime_type,
                bytes_data=decrypted_bytes,
                file_size=row.file_size,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    @property
    def is_openai_google_supported(self) -> bool:
        """Check if the file is supported by OpenAI and Google.

        OpenAI and Google both support images, PDFs, text files, and audio files.

        This property automatically excludes transcription files.
        """
        if self.file_id.endswith("_transcription"):
            return False

        return (
            self.mime_type.startswith("image/")
            or self.mime_type.startswith("application/pdf")
            or self.mime_type.startswith("text/")
            or self.mime_type.startswith("audio/")
        )

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

    @db_retry()
    async def save(self) -> MediaFile:
        """Save or update the media file in the database with encrypted content.

        Returns:
            MediaFile instance refreshed from database
        """
        now = datetime.now(UTC)

        # Encrypt content for storage
        encrypted_content_base64 = self.encrypt_content()

        async with async_database() as db_conn:
            stmt = pg_insert(MediaFilesTable).values(
                object_key=self.object_key,
                file_id=self.file_id,
                file_unique_id=self.file_unique_id,
                chat_id=self.chat.id,
                message_id=self.message_id,
                mime_type=self.mime_type,
                file_size=self.file_size,
                encrypted_content_base64=encrypted_content_base64,
                created_at=self.created_at,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["object_key"],
                set_={
                    "file_unique_id": stmt.excluded.file_unique_id,
                    "mime_type": stmt.excluded.mime_type,
                    "file_size": stmt.excluded.file_size,
                    "encrypted_content_base64": stmt.excluded.encrypted_content_base64,
                    "updated_at": now,
                },
            ).returning(MediaFilesTable.id)

            result = await db_conn.execute(stmt)
            row_id = result.scalar_one()

        # Return refreshed from database using get_by_id
        return await MediaFile.get_by_id(chat=self.chat, media_file_id=row_id)

    @classmethod
    @db_retry()
    async def get_by_message(
        cls,
        chat: Chat,
        *,
        message_id: int,
    ) -> list[MediaFile]:
        """Retrieve all media files for a message, auto-decrypted.

        Args:
            chat: Chat object (provides encryption key)
            message_id: Internal message ID (FK to messages.id)

        Returns:
            List of decrypted MediaFile instances
        """
        # Query for IDs only
        async with async_database() as db_conn:
            stmt = select(MediaFilesTable.id).where(
                MediaFilesTable.chat_id == chat.id,
                MediaFilesTable.message_id == message_id,
            )
            result = await db_conn.execute(stmt)
            media_file_ids = result.scalars().all()

        # Hydrate via get_by_id concurrently
        media_file_tasks = [cls.get_by_id(chat, media_file_id=mf_id) for mf_id in media_file_ids]
        media_files_with_none = await asyncio.gather(*media_file_tasks)
        media_files = [mf for mf in media_files_with_none if mf is not None]

        return media_files
