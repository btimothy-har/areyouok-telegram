import base64
import hashlib
from datetime import UTC
from datetime import datetime

import magic
from cachetools import TTLCache
from cryptography.fernet import Fernet
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
from areyouok_telegram.encryption.exceptions import ContentNotDecryptedError
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
    encrypted_content_base64 = Column(Text, nullable=False)

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)
    last_accessed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # TTL cache for decrypted content (2 hours TTL, max 1000 entries)
    _data_cache: TTLCache[str, bytes] = TTLCache(maxsize=1000, ttl=2 * 60 * 60)

    @staticmethod
    def generate_file_key(chat_id: str, message_id: str, file_unique_id: str, encrypted_content_base64: str) -> str:
        """Generate a unique key for a file based on its chat ID, message ID, unique ID, and encrypted content."""
        key_string = f"{chat_id}:{message_id}:{file_unique_id}:{encrypted_content_base64}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    @classmethod
    def encrypt_content(cls, content_bytes: bytes, user_encryption_key: str) -> str:
        """Encrypt the byte content using the user's encryption key.

        Args:
            content_bytes: The raw byte content to encrypt
            user_encryption_key: The user's Fernet encryption key

        Returns:
            str: The encrypted content as base64-encoded string for storage
        """
        fernet = Fernet(user_encryption_key.encode())
        encrypted_bytes = fernet.encrypt(content_bytes)
        return base64.b64encode(encrypted_bytes).decode("ascii")

    def decrypt_content(self, user_encryption_key: str) -> bytes:
        """Decrypt the content using the user's encryption key.

        Args:
            user_encryption_key: The user's Fernet encryption key

        Returns:
            bytes: The decrypted file content as bytes, or None if no encrypted content
        """
        fernet = Fernet(user_encryption_key.encode())
        encrypted_bytes = base64.b64decode(self.encrypted_content_base64.encode("ascii"))
        decrypted_bytes = fernet.decrypt(encrypted_bytes)

        self._data_cache[self.file_key] = decrypted_bytes
        return decrypted_bytes

    @property
    def bytes_data(self) -> bytes:
        """Get the decrypted file content as bytes.

        Returns:
            bytes: The decrypted file content as bytes

        Raises:
            ContentNotDecryptedError: If content hasn't been decrypted yet
        """
        decrypted_bytes = self._data_cache.get(self.file_key)
        if decrypted_bytes is None:
            # If not in cache, content needs to be decrypted first
            raise ContentNotDecryptedError(self.file_key)

        return decrypted_bytes

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
        user_encryption_key: str,
        *,
        file_id: str,
        file_unique_id: str,
        chat_id: str,
        message_id: str,
        file_size: int,
        content_bytes: bytes,
    ):
        """Create a media file entry with encrypted content.

        Args:
            db_conn: Database connection
            user_encryption_key: The user's Fernet encryption key
            file_id: Telegram file ID
            file_unique_id: Telegram unique file ID
            chat_id: Chat ID where the file was sent
            message_id: Message ID containing the file
            file_size: Size of the file in bytes
            content_bytes: Raw file content as bytes
        """
        now = datetime.now(UTC)

        # Use python-magic to get MIME type
        mime_type = magic.from_buffer(content_bytes, mime=True)
        encrypted_content_base64 = cls.encrypt_content(content_bytes, user_encryption_key)

        # Generate file key with encrypted content
        file_key = cls.generate_file_key(chat_id, message_id, file_unique_id, encrypted_content_base64 or "")

        # Create new media entry
        stmt = pg_insert(cls).values(
            file_key=file_key,
            file_id=file_id,
            file_unique_id=file_unique_id,
            chat_id=chat_id,
            message_id=message_id,
            mime_type=mime_type,
            file_size=file_size,
            encrypted_content_base64=encrypted_content_base64,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["file_key"],
            set_={
                "file_unique_id": stmt.excluded.file_unique_id,
                "mime_type": stmt.excluded.mime_type,
                "file_size": stmt.excluded.file_size,
                "encrypted_content_base64": stmt.excluded.encrypted_content_base64,
                "updated_at": datetime.now(UTC),
            },
        )

        await db_conn.execute(stmt)

    @classmethod
    @traced(extract_args=["chat_id", "message_id"])
    async def get_by_message_id(cls, db_conn: AsyncSession, *, chat_id: str, message_id: str) -> list["MediaFiles"]:
        """Retrieve all media files by chat_id and message_id and update last_accessed_at."""
        stmt = select(cls).where((cls.chat_id == chat_id) & (cls.message_id == message_id))
        result = await db_conn.execute(stmt)
        media_files = result.scalars().all()

        # Update last_accessed_at for all found media files
        if media_files:
            media_ids = [media.id for media in media_files]
            await cls.bulk_update_last_accessed(db_conn, media_ids=media_ids)

        return media_files

    @classmethod
    @traced(extract_args=["media_ids"])
    async def bulk_update_last_accessed(cls, db_conn: AsyncSession, *, media_ids: list[int]) -> None:
        """Update last_accessed_at timestamp for given media IDs.

        Args:
            db_conn: Database connection
            media_ids: List of media record IDs to update
        """
        if not media_ids:
            return

        stmt = update(cls).where(cls.id.in_(media_ids)).values(last_accessed_at=datetime.now(UTC))
        await db_conn.execute(stmt)
