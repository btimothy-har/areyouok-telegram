"""Tests for MediaFiles model."""

import base64
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet, InvalidToken

from areyouok_telegram.data.models.media import MediaFiles
from areyouok_telegram.encryption.exceptions import ContentNotDecryptedError


class TestMediaFiles:
    """Test MediaFiles model."""

    def test_generate_file_key(self):
        """Test file key generation."""
        chat_id = "123"
        message_id = "456"
        file_unique_id = "unique789"
        encrypted_content = "encrypted_test_content"

        key_string = f"{chat_id}:{message_id}:{file_unique_id}:{encrypted_content}"
        expected = hashlib.sha256(key_string.encode()).hexdigest()
        assert MediaFiles.generate_file_key(chat_id, message_id, file_unique_id, encrypted_content) == expected

    def test_encrypt_content_base64(self):
        """Test byte content encryption."""
        content_bytes = b"test content"
        user_key = Fernet.generate_key().decode("utf-8")

        encrypted = MediaFiles.encrypt_content(content_bytes=content_bytes, chat_encryption_key=user_key)

        # Should be a base64 string
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0

        # Should be able to decrypt it back
        fernet = Fernet(user_key.encode())
        encrypted_bytes = base64.b64decode(encrypted.encode("ascii"))
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        assert decrypted_bytes == content_bytes

    def test_decrypt_content_base64(self):
        """Test content decryption."""
        content_bytes = b"another test content"
        user_key = Fernet.generate_key().decode("utf-8")

        # First encrypt
        encrypted = MediaFiles.encrypt_content(content_bytes=content_bytes, chat_encryption_key=user_key)

        # Create media instance with encrypted content
        media = MediaFiles()
        media.encrypted_content_base64 = encrypted
        media.file_key = "test_file_key"

        # Decrypt should return original bytes
        decrypted = media.decrypt_content(chat_encryption_key=user_key)
        assert decrypted == content_bytes

    def test_decrypt_content_base64_no_encrypted_content(self):
        """Test decrypt_content with invalid content."""

        media = MediaFiles()
        media.encrypted_content_base64 = "invalid_base64"
        media.file_key = "test_file_key"
        user_key = Fernet.generate_key().decode("utf-8")

        with pytest.raises((InvalidToken, ValueError)):
            media.decrypt_content(chat_encryption_key=user_key)

    def test_bytes_data_with_content(self):
        """Test decoding encrypted base64 content to bytes."""
        # Clear the cache to ensure clean test
        MediaFiles._data_cache.clear()

        media = MediaFiles()
        test_data = b"test content"
        user_key = Fernet.generate_key().decode("utf-8")

        # Encrypt the content
        media.encrypted_content_base64 = MediaFiles.encrypt_content(
            content_bytes=test_data, chat_encryption_key=user_key
        )
        media.file_key = "test_file_key_for_content"

        # First decrypt the content
        media.decrypt_content(chat_encryption_key=user_key)

        # Now bytes_data property should return the decrypted data
        assert media.bytes_data == test_data

    def test_bytes_data_without_content(self):
        """Test bytes_data raises error when content not decrypted."""

        # Clear the cache to ensure clean test
        MediaFiles._data_cache.clear()

        media = MediaFiles()
        media.file_key = "test_file_key_unique"
        media.encrypted_content_base64 = "some_encrypted_data"

        with pytest.raises(ContentNotDecryptedError):
            _ = media.bytes_data

    def test_is_anthropic_supported_image(self):
        """Test image files are marked as Anthropic-supported."""
        media = MediaFiles()
        media.mime_type = "image/png"

        assert media.is_anthropic_supported is True

    def test_is_anthropic_supported_pdf(self):
        """Test PDF files are marked as Anthropic-supported."""
        media = MediaFiles()
        media.mime_type = "application/pdf"

        assert media.is_anthropic_supported is True

    def test_is_anthropic_supported_text(self):
        """Test text files are marked as Anthropic-supported."""
        media = MediaFiles()
        media.mime_type = "text/plain"

        assert media.is_anthropic_supported is True

    def test_is_anthropic_supported_unsupported(self):
        """Test unsupported files are marked correctly."""
        media = MediaFiles()
        media.mime_type = "video/mp4"

        assert media.is_anthropic_supported is False

    @pytest.mark.asyncio
    async def test_create_file_with_content(self, mock_db_session):
        """Test creating a media file with content."""
        test_content = b"test file content"
        user_key = Fernet.generate_key().decode("utf-8")

        # Mock magic.from_buffer
        with patch("areyouok_telegram.data.models.media.magic.from_buffer") as mock_magic:
            mock_magic.return_value = "text/plain"

            mock_result = AsyncMock()
            mock_db_session.execute.return_value = mock_result

            await MediaFiles.create_file(
                mock_db_session,
                user_key,
                file_id="file123",
                file_unique_id="unique123",
                chat_id="chat456",
                message_id="msg789",
                file_size=len(test_content),
                content_bytes=test_content,
            )

            # Verify execute was called
            mock_db_session.execute.assert_called_once()

            # Verify magic was called with the content
            mock_magic.assert_called_once_with(test_content, mime=True)

            # Verify the statement is for media_files table
            call_args = mock_db_session.execute.call_args[0][0]
            assert hasattr(call_args, "table")
            assert call_args.table.name == "media_files"

    @pytest.mark.asyncio
    async def test_create_file_without_content(self, mock_db_session):
        """Test creating a media file without content."""
        user_key = Fernet.generate_key().decode("utf-8")

        with patch("areyouok_telegram.data.models.media.magic.from_buffer") as mock_magic:
            mock_magic.return_value = "application/octet-stream"  # Default MIME for empty
            mock_result = AsyncMock()
            mock_db_session.execute.return_value = mock_result

            await MediaFiles.create_file(
                mock_db_session,
                user_key,
                file_id="file456",
                file_unique_id="unique456",
                chat_id="chat789",
                message_id="msg012",
                file_size=0,
                content_bytes=b"",  # Empty bytes instead of None
            )

            # Verify execute was called
            mock_db_session.execute.assert_called_once()

            # Magic should be called with empty bytes
            mock_magic.assert_called_once_with(b"", mime=True)

    @pytest.mark.asyncio
    async def test_get_by_message_id_found(self, mock_db_session):
        """Test retrieving media files by message ID."""
        # Create mock media files
        mock_media1 = MagicMock(spec=MediaFiles)
        mock_media1.id = 1
        mock_media2 = MagicMock(spec=MediaFiles)
        mock_media2.id = 2

        # Setup mock chain for execute().scalars().all()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_media1, mock_media2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await MediaFiles.get_by_message_id(mock_db_session, chat_id="chat123", message_id="msg456")

        assert result == [mock_media1, mock_media2]

        # Verify two execute calls: one for select, one for update
        assert mock_db_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_get_by_message_id_not_found(self, mock_db_session):
        """Test retrieving media files when none found."""
        # Setup mock chain for execute().scalars().all() returning empty list
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await MediaFiles.get_by_message_id(mock_db_session, chat_id="chat999", message_id="msg999")

        assert result == []

        # Only one execute call for select, no update since no media found
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_update_last_accessed_with_ids(self, mock_db_session):
        """Test bulk updating last accessed timestamp."""
        mock_result = AsyncMock()
        mock_db_session.execute.return_value = mock_result

        await MediaFiles.bulk_update_last_accessed(mock_db_session, media_ids=[1, 2, 3])

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify it's an update statement
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "table")
        assert call_args.table.name == "media_files"

    @pytest.mark.asyncio
    async def test_bulk_update_last_accessed_empty_list(self, mock_db_session):
        """Test bulk update with empty list does nothing."""
        await MediaFiles.bulk_update_last_accessed(mock_db_session, media_ids=[])

        # Verify execute was not called
        mock_db_session.execute.assert_not_called()

    def test_is_openai_google_supported_transcription_files_excluded(self):
        """Test that transcription files are excluded regardless of mime type."""
        # Test with image mime type but transcription file_id
        media = MediaFiles()
        media.file_id = "image_file_123_transcription"
        media.mime_type = "image/png"
        assert media.is_openai_google_supported is False

        # Test with PDF mime type but transcription file_id
        media = MediaFiles()
        media.file_id = "document_456_transcription"
        media.mime_type = "application/pdf"
        assert media.is_openai_google_supported is False

        # Test with text mime type but transcription file_id
        media = MediaFiles()
        media.file_id = "text_789_transcription"
        media.mime_type = "text/plain"
        assert media.is_openai_google_supported is False

        # Test with audio mime type but transcription file_id
        media = MediaFiles()
        media.file_id = "audio_012_transcription"
        media.mime_type = "audio/mp3"
        assert media.is_openai_google_supported is False

    def test_is_openai_google_supported_image_files(self):
        """Test that image files are supported."""
        media = MediaFiles()
        media.file_id = "image_file_123"
        media.mime_type = "image/png"
        assert media.is_openai_google_supported is True

        media.mime_type = "image/jpeg"
        assert media.is_openai_google_supported is True

        media.mime_type = "image/gif"
        assert media.is_openai_google_supported is True

    def test_is_openai_google_supported_pdf_files(self):
        """Test that PDF files are supported."""
        media = MediaFiles()
        media.file_id = "document_456"
        media.mime_type = "application/pdf"
        assert media.is_openai_google_supported is True

    def test_is_openai_google_supported_text_files(self):
        """Test that text files are supported."""
        media = MediaFiles()
        media.file_id = "text_789"
        media.mime_type = "text/plain"
        assert media.is_openai_google_supported is True

        media.mime_type = "text/html"
        assert media.is_openai_google_supported is True

    def test_is_openai_google_supported_audio_files(self):
        """Test that audio files are supported."""
        media = MediaFiles()
        media.file_id = "audio_012"
        media.mime_type = "audio/mp3"
        assert media.is_openai_google_supported is True

        media.mime_type = "audio/wav"
        assert media.is_openai_google_supported is True

    def test_is_openai_google_supported_unsupported_files(self):
        """Test that unsupported files return False."""
        media = MediaFiles()
        media.file_id = "video_345"
        media.mime_type = "video/mp4"
        assert media.is_openai_google_supported is False

        media.mime_type = "application/zip"
        assert media.is_openai_google_supported is False
