"""Tests for unsupported media handling."""

from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from areyouok_telegram.data import MediaFiles
from areyouok_telegram.jobs.utils import get_unsupported_media_from_messages


class TestUnsupportedMediaHandling:
    """Test unsupported media detection and handling."""

    @pytest.mark.asyncio
    async def test_get_unsupported_media_from_messages_video(self):
        """Test detection of video files."""
        # Create mock messages
        msg1 = MagicMock()
        msg1.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        msg1.message_id = 100
        msg1.from_user = MagicMock()
        msg1.from_user.id = 123456789
        msg1.chat = MagicMock()
        msg1.chat.id = "123456"

        messages = [msg1]

        # Mock media files
        video_file = MagicMock()
        video_file.mime_type = "video/mp4"

        with patch.object(MediaFiles, "get_by_message_id", new_callable=AsyncMock) as mock_get_media:
            mock_get_media.return_value = [video_file]

            result = await get_unsupported_media_from_messages(None, messages)

            assert result == ["video/mp4"]
            mock_get_media.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_unsupported_media_from_messages_audio_now_supported(self):
        """Test that audio files are now supported and not returned as unsupported."""
        # Create mock messages
        msg1 = MagicMock()
        msg1.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        msg1.message_id = 100
        msg1.from_user = MagicMock()
        msg1.from_user.id = 123456789
        msg1.chat = MagicMock()
        msg1.chat.id = "123456"

        messages = [msg1]

        # Mock media files
        audio_file = MagicMock()
        audio_file.mime_type = "audio/mpeg"

        with patch.object(MediaFiles, "get_by_message_id", new_callable=AsyncMock) as mock_get_media:
            mock_get_media.return_value = [audio_file]

            result = await get_unsupported_media_from_messages(None, messages)

            # Audio is now supported, so should return empty list
            assert result == []

    @pytest.mark.asyncio
    async def test_get_unsupported_media_from_messages_mixed(self):
        """Test detection of multiple unsupported media types."""
        # Create mock messages
        msg1 = MagicMock()
        msg1.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        msg1.message_id = 100
        msg1.from_user = MagicMock()
        msg1.from_user.id = 123456789
        msg1.chat = MagicMock()
        msg1.chat.id = "123456"

        msg2 = MagicMock()
        msg2.date = datetime(2025, 1, 15, 10, 1, 0, tzinfo=UTC)
        msg2.message_id = 101
        msg2.from_user = MagicMock()
        msg2.from_user.id = 123456789
        msg2.chat = MagicMock()
        msg2.chat.id = "123456"

        messages = [msg1, msg2]

        # Mock media files for first message
        video_file = MagicMock()
        video_file.mime_type = "video/mp4"

        # Mock media files for second message - use a document instead of audio since audio is now supported
        document_file = MagicMock()
        document_file.mime_type = "application/msword"

        with patch.object(MediaFiles, "get_by_message_id", new_callable=AsyncMock) as mock_get_media:
            mock_get_media.side_effect = [[video_file], [document_file]]

            result = await get_unsupported_media_from_messages(None, messages)

            assert result == ["video/mp4", "application/msword"]
            assert mock_get_media.call_count == 2

    @pytest.mark.asyncio
    async def test_get_unsupported_media_ignores_supported_types(self):
        """Test that supported media types are ignored."""
        # Create mock messages
        msg1 = MagicMock()
        msg1.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        msg1.message_id = 100
        msg1.from_user = MagicMock()
        msg1.from_user.id = 123456789
        msg1.chat = MagicMock()
        msg1.chat.id = "123456"

        messages = [msg1]

        # Mock media files with mixed types
        image_file = MagicMock()
        image_file.mime_type = "image/png"

        pdf_file = MagicMock()
        pdf_file.mime_type = "application/pdf"

        text_file = MagicMock()
        text_file.mime_type = "text/plain"

        video_file = MagicMock()
        video_file.mime_type = "video/mp4"

        # Add audio file to test it's now supported
        audio_file = MagicMock()
        audio_file.mime_type = "audio/mpeg"

        with patch.object(MediaFiles, "get_by_message_id", new_callable=AsyncMock) as mock_get_media:
            mock_get_media.return_value = [image_file, pdf_file, text_file, video_file, audio_file]

            result = await get_unsupported_media_from_messages(None, messages)

            # Only video should be in the result (audio is now supported)
            assert result == ["video/mp4"]

    @pytest.mark.asyncio
    async def test_get_unsupported_media_with_since_timestamp(self):
        """Test filtering messages by timestamp."""
        # Create mock messages
        msg1 = MagicMock()
        msg1.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        msg1.from_user = MagicMock()
        msg1.from_user.id = 123456789
        msg1.chat = MagicMock()
        msg1.chat.id = "123456"
        msg1.message_id = 100

        msg2 = MagicMock()
        msg2.date = datetime(2025, 1, 15, 10, 5, 0, tzinfo=UTC)  # 5 minutes later
        msg2.from_user = MagicMock()
        msg2.from_user.id = 123456789
        msg2.chat = MagicMock()
        msg2.chat.id = "123456"
        msg2.message_id = 101

        messages = [msg1, msg2]

        # Set since_timestamp between the two messages
        since_timestamp = datetime(2025, 1, 15, 10, 2, 0, tzinfo=UTC)

        # Mock media files
        video_file = MagicMock()
        video_file.mime_type = "video/mp4"

        with patch.object(MediaFiles, "get_by_message_id", new_callable=AsyncMock) as mock_get_media:
            mock_get_media.return_value = [video_file]

            result = await get_unsupported_media_from_messages(None, messages, since_timestamp)

            # Should only check msg2 (after since_timestamp)
            assert result == ["video/mp4"]
            assert mock_get_media.call_count == 1
            mock_get_media.assert_called_with(None, chat_id="123456", message_id="101")

    @pytest.mark.asyncio
    async def test_get_unsupported_media_unknown_mime_type(self):
        """Test handling of unknown mime types."""
        # Create mock messages
        msg1 = MagicMock()
        msg1.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        msg1.message_id = 100
        msg1.from_user = MagicMock()
        msg1.from_user.id = 123456789
        msg1.chat = MagicMock()
        msg1.chat.id = "123456"

        messages = [msg1]

        # Mock media files with unknown type
        unknown_file = MagicMock()
        unknown_file.mime_type = "application/octet-stream"

        with patch.object(MediaFiles, "get_by_message_id", new_callable=AsyncMock) as mock_get_media:
            mock_get_media.return_value = [unknown_file]

            result = await get_unsupported_media_from_messages(None, messages)

            # Should return the full mime type for unknown types
            assert result == ["application/octet-stream"]

    @pytest.mark.asyncio
    async def test_get_unsupported_media_no_user(self):
        """Test that messages without from_user are skipped."""
        # Create mock messages
        msg1 = MagicMock()
        msg1.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        msg1.message_id = 100
        msg1.from_user = None  # No user
        msg1.chat = MagicMock()
        msg1.chat.id = "123456"

        messages = [msg1]

        with patch.object(MediaFiles, "get_by_message_id", new_callable=AsyncMock) as mock_get_media:
            result = await get_unsupported_media_from_messages(None, messages)

            # Should not check media for messages without users
            assert result == []
            mock_get_media.assert_not_called()
