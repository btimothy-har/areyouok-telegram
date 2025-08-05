"""Tests for MediaFiles data model."""

import base64
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from areyouok_telegram.data import MediaFiles


@pytest.fixture
def mock_media_files():
    """Create mock MediaFiles objects with different MIME types."""
    # Image file (compatible)
    image_media = MagicMock(spec=MediaFiles)
    image_media.file_id = "image_123"
    image_media.mime_type = "image/jpeg"
    image_media.content_base64 = base64.b64encode(b"fake_image_data").decode()
    image_media.bytes_data = b"fake_image_data"

    # PDF file (compatible)
    pdf_media = MagicMock(spec=MediaFiles)
    pdf_media.file_id = "pdf_123"
    pdf_media.mime_type = "application/pdf"
    pdf_media.content_base64 = base64.b64encode(b"fake_pdf_data").decode()
    pdf_media.bytes_data = b"fake_pdf_data"

    # Audio file (not compatible)
    audio_media = MagicMock(spec=MediaFiles)
    audio_media.file_id = "audio_123"
    audio_media.mime_type = "audio/ogg"
    audio_media.content_base64 = base64.b64encode(b"fake_audio_data").decode()
    audio_media.bytes_data = b"fake_audio_data"

    # Video file (not compatible)
    video_media = MagicMock(spec=MediaFiles)
    video_media.file_id = "video_123"
    video_media.mime_type = "video/mp4"
    video_media.content_base64 = base64.b64encode(b"fake_video_data").decode()
    video_media.bytes_data = b"fake_video_data"

    # Text file (transcription - not compatible with agent)
    text_media = MagicMock(spec=MediaFiles)
    text_media.file_id = "voice_123_transcription"
    text_media.mime_type = "text/plain"
    text_media.content_base64 = base64.b64encode(b"[Transcribed Audio] Test transcription").decode()
    text_media.bytes_data = b"[Transcribed Audio] Test transcription"

    return [image_media, pdf_media, audio_media, video_media, text_media]


class TestMediaFiles:
    """Test MediaFiles functionality."""

    @pytest.mark.asyncio
    async def test_create_file_with_individual_params(self, mock_async_database_session):
        """Test creating a file with individual parameters."""
        # Mock magic.from_buffer to detect MIME type
        with patch("areyouok_telegram.data.media.magic.from_buffer") as mock_from_buffer:
            mock_from_buffer.return_value = "image/jpeg"

            await MediaFiles.create_file(
                session=mock_async_database_session,
                file_id="test_123",
                file_unique_id="test_unique_123",
                chat_id="123456",
                message_id="789",
                file_size=1024,
                content_bytes=b"fake_image_data",
            )

            # Verify magic was called with correct parameters
            mock_from_buffer.assert_called_once_with(b"fake_image_data", mime=True)

            # Verify database operations were called
            mock_async_database_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_agent_compatible_media(self, mock_async_database_session, mock_media_files):
        """Test filtering media files for agent compatibility."""
        # Mock get_by_message_id to return all media types
        with patch.object(MediaFiles, "get_by_message_id", return_value=mock_media_files):
            result = await MediaFiles.get_agent_compatible_media(
                mock_async_database_session, chat_id="123456", message_id="789"
            )

            # Should only return image and PDF files
            assert len(result) == 2
            assert result[0].mime_type == "image/jpeg"
            assert result[1].mime_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_get_agent_compatible_media_empty(self, mock_async_database_session):
        """Test get_agent_compatible_media with no media files."""
        # Mock get_by_message_id to return empty list
        with patch.object(MediaFiles, "get_by_message_id", return_value=[]):
            result = await MediaFiles.get_agent_compatible_media(
                mock_async_database_session, chat_id="123456", message_id="789"
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_get_agent_compatible_media_no_compatible(self, mock_async_database_session):
        """Test get_agent_compatible_media with only incompatible media."""
        # Create only audio/video media
        audio_media = MagicMock(spec=MediaFiles)
        audio_media.mime_type = "audio/ogg"

        video_media = MagicMock(spec=MediaFiles)
        video_media.mime_type = "video/mp4"

        with patch.object(MediaFiles, "get_by_message_id", return_value=[audio_media, video_media]):
            result = await MediaFiles.get_agent_compatible_media(
                mock_async_database_session, chat_id="123456", message_id="789"
            )

            assert result == []

    def test_bytes_data_property(self):
        """Test bytes_data property returns decoded content."""
        media_file = MediaFiles()
        media_file.content_base64 = base64.b64encode(b"test content").decode()

        result = media_file.bytes_data
        assert result == b"test content"

    def test_bytes_data_property_none(self):
        """Test bytes_data property returns None when no content."""
        media_file = MediaFiles()
        media_file.content_base64 = None

        result = media_file.bytes_data
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_file_id_found(self, mock_async_database_session):
        """Test get_by_file_id when media is found."""
        # Create mock media file
        mock_media = MagicMock(spec=MediaFiles)
        mock_media.id = 123
        mock_media.file_id = "test_file_123"

        # Mock the execute result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        mock_async_database_session.execute.return_value = mock_result

        # Mock update_last_accessed
        with patch.object(MediaFiles, "update_last_accessed") as mock_update:
            result = await MediaFiles.get_by_file_id(mock_async_database_session, "test_file_123")

            assert result == mock_media
            # Verify update_last_accessed was called with the media ID
            mock_update.assert_called_once_with(mock_async_database_session, [123])

    @pytest.mark.asyncio
    async def test_get_by_file_id_not_found(self, mock_async_database_session):
        """Test get_by_file_id when media is not found."""
        # Mock the execute result to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_database_session.execute.return_value = mock_result

        # Mock update_last_accessed
        with patch.object(MediaFiles, "update_last_accessed") as mock_update:
            result = await MediaFiles.get_by_file_id(mock_async_database_session, "nonexistent_file")

            assert result is None
            # Verify update_last_accessed was NOT called
            mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_by_message_id_with_media(self, mock_async_database_session):
        """Test get_by_message_id when media files are found."""
        # Create mock media files
        mock_media1 = MagicMock(spec=MediaFiles)
        mock_media1.id = 1
        mock_media2 = MagicMock(spec=MediaFiles)
        mock_media2.id = 2

        # Mock the execute result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_media1, mock_media2]
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Mock update_last_accessed
        with patch.object(MediaFiles, "update_last_accessed") as mock_update:
            result = await MediaFiles.get_by_message_id(mock_async_database_session, "123456", "789")

            assert result == [mock_media1, mock_media2]
            # Verify update_last_accessed was called with both media IDs
            mock_update.assert_called_once_with(mock_async_database_session, [1, 2])

    @pytest.mark.asyncio
    async def test_get_by_message_id_no_media(self, mock_async_database_session):
        """Test get_by_message_id when no media files are found."""
        # Mock the execute result to return empty list
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Mock update_last_accessed
        with patch.object(MediaFiles, "update_last_accessed") as mock_update:
            result = await MediaFiles.get_by_message_id(mock_async_database_session, "123456", "789")

            assert result == []
            # Verify update_last_accessed was NOT called
            mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_last_accessed_with_ids(self, mock_async_database_session):
        """Test update_last_accessed with media IDs."""
        await MediaFiles.update_last_accessed(mock_async_database_session, [1, 2, 3])

        # Verify execute was called
        mock_async_database_session.execute.assert_called_once()

        # Get the statement that was executed
        executed_stmt = mock_async_database_session.execute.call_args[0][0]

        # Verify it's an update statement (checking the string representation)
        stmt_str = str(executed_stmt)
        assert "UPDATE" in stmt_str
        assert "media_files" in stmt_str
        assert "last_accessed_at" in stmt_str

    @pytest.mark.asyncio
    async def test_update_last_accessed_empty_list(self, mock_async_database_session):
        """Test update_last_accessed with empty media IDs list."""
        await MediaFiles.update_last_accessed(mock_async_database_session, [])

        # Verify execute was NOT called for empty list
        mock_async_database_session.execute.assert_not_called()
