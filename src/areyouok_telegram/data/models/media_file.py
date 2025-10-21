"""MediaFile Pydantic model for uploaded media content."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime

import pydantic
from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import MediaFilesTable
from areyouok_telegram.data.models.chat import Chat
from areyouok_telegram.logging import traced


class MediaFile(pydantic.BaseModel):
    """Media file model for uploaded media content."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # Required fields
    chat: Chat
    message_id: int  # FK to messages.id
    file_id: str
    file_unique_id: str
    mime_type: str
    bytes_data: bytes

    # Optional fields
    id: int = 0
    file_size: int | None = None
    created_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    last_accessed_at: datetime | None = None

    @property
    def chat_id(self) -> int:
        """Get chat_id from the Chat object."""
        return self.chat.id

    @staticmethod
    def generate_object_key(chat_id: int, message_id: int, file_unique_id: str) -> str:
        """Generate a unique object key using internal IDs."""
        return hashlib.sha256(f"media:{chat_id}:{message_id}:{file_unique_id}".encode()).hexdigest()

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

    @traced(extract_args=["chat_id", "message_id", "file_id"])
    async def save(self) -> MediaFile:
        """Save or update the media file in the database with encrypted content.

        Returns:
            MediaFile instance refreshed from database
        """
        now = datetime.now(UTC)

        # Encrypt content for storage
        encrypted_content_base64 = self.encrypt_content()
        object_key = self.generate_object_key(self.chat.id, self.message_id, self.file_unique_id)

        async with async_database() as db_conn:
            stmt = pg_insert(MediaFilesTable).values(
                object_key=object_key,
                file_id=self.file_id,
                file_unique_id=self.file_unique_id,
                chat_id=self.chat.id,
                message_id=self.message_id,
                mime_type=self.mime_type,
                file_size=self.file_size,
                encrypted_content_base64=encrypted_content_base64,
                created_at=self.created_at,
                updated_at=now,
                last_accessed_at=self.last_accessed_at,
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
            ).returning(MediaFilesTable)

            result = await db_conn.execute(stmt)
            row = result.scalar_one()

            # Return with decrypted content
            encryption_key = self.chat.retrieve_key()
            decrypted_bytes = self.decrypt_content(row.encrypted_content_base64, encryption_key)

            return MediaFile(
                id=row.id,
                chat=self.chat,
                message_id=row.message_id,
                file_id=row.file_id,
                file_unique_id=row.file_unique_id,
                mime_type=row.mime_type,
                bytes_data=decrypted_bytes,
                file_size=row.file_size,
                created_at=row.created_at,
                updated_at=row.updated_at,
                last_accessed_at=row.last_accessed_at,
            )

    @classmethod
    @traced(extract_args=["chat", "message_id"])
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
        async with async_database() as db_conn:
            stmt = select(MediaFilesTable).where(
                MediaFilesTable.chat_id == chat.id,
                MediaFilesTable.message_id == message_id,
            )
            result = await db_conn.execute(stmt)
            rows = result.scalars().all()

            # Convert to MediaFile instances and decrypt
            encryption_key = chat.retrieve_key()
            media_files = []

            for row in rows:
                decrypted_bytes = cls.decrypt_content(row.encrypted_content_base64, encryption_key)

                media_file = MediaFile(
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
                    last_accessed_at=row.last_accessed_at,
                )
                media_files.append(media_file)

            # Update last_accessed_at for all found media files
            if media_files:
                media_ids = [m.id for m in media_files]
                await cls._bulk_update_last_accessed(media_ids)

            return media_files

    @classmethod
    async def _bulk_update_last_accessed(cls, media_ids: list[int]) -> None:
        """Update last_accessed_at timestamp for given media IDs.

        Args:
            media_ids: List of media record IDs to update
        """
        if not media_ids:
            return

        async with async_database() as db_conn:
            stmt = (
                update(MediaFilesTable)
                .where(MediaFilesTable.id.in_(media_ids))
                .values(last_accessed_at=datetime.now(UTC))
            )
            await db_conn.execute(stmt)
