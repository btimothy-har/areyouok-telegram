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
