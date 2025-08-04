"""Tests for handler utilities including voice transcription."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from areyouok_telegram.handlers.utils import VoiceNotProcessableError
from areyouok_telegram.handlers.utils import extract_media_from_telegram_message
from areyouok_telegram.handlers.utils import transcribe_voice_data_sync


class TestVoiceTranscription:
    """Test voice transcription functionality."""

    @patch("areyouok_telegram.handlers.utils.openai.OpenAI")
    @patch("areyouok_telegram.handlers.utils.AudioSegment.from_ogg")
    def test_transcribe_voice_data_sync_success(self, mock_from_ogg, mock_openai_class):
        """Test successful voice transcription."""
        # Mock audio segment
        mock_audio = MagicMock()
        mock_audio.__len__.return_value = 5 * 60 * 1000  # 5 minutes
        mock_audio.__getitem__.return_value = mock_audio
        mock_audio.export = MagicMock()
        mock_from_ogg.return_value = mock_audio

        # Mock OpenAI client
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = "This is a test transcription"

        # Test transcription
        voice_data = b"fake_ogg_data"
        result = transcribe_voice_data_sync(voice_data)

        assert result == "[Transcribed Audio] This is a test transcription"
        mock_client.audio.transcriptions.create.assert_called_once()

        # Verify model is gpt-4o-transcribe
        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-transcribe"

    @patch("areyouok_telegram.handlers.utils.openai.OpenAI")
    @patch("areyouok_telegram.handlers.utils.AudioSegment.from_ogg")
    def test_transcribe_voice_data_sync_long_audio(self, mock_from_ogg, mock_openai_class):
        """Test transcription of audio longer than 10 minutes."""
        # Mock audio segment (15 minutes)
        mock_audio = MagicMock()
        mock_audio.__len__.return_value = 15 * 60 * 1000  # 15 minutes

        # Mock segments
        mock_segment1 = MagicMock()
        mock_segment2 = MagicMock()
        mock_audio.__getitem__.side_effect = [mock_segment1, mock_segment2]

        mock_from_ogg.return_value = mock_audio

        # Mock OpenAI client
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.audio.transcriptions.create.side_effect = [
            "First segment transcription",
            "Second segment transcription",
        ]

        # Test transcription
        voice_data = b"fake_long_ogg_data"
        result = transcribe_voice_data_sync(voice_data)

        assert result == "[Transcribed Audio] First segment transcription Second segment transcription"
        assert mock_client.audio.transcriptions.create.call_count == 2

    @patch("areyouok_telegram.handlers.utils.openai.OpenAI")
    @patch("areyouok_telegram.handlers.utils.AudioSegment.from_ogg")
    def test_transcribe_voice_data_sync_error(self, mock_from_ogg, mock_openai_class):  # noqa: ARG002
        """Test transcription error handling."""
        # Mock audio processing to raise an error
        mock_from_ogg.side_effect = Exception("Audio processing failed")

        # Test transcription
        voice_data = b"fake_bad_ogg_data"

        with pytest.raises(VoiceNotProcessableError):
            transcribe_voice_data_sync(voice_data)


class TestExtractMediaFromTelegramMessage:
    """Test media extraction from Telegram messages."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.MediaFiles.create_file")
    async def test_extract_voice_message(self, mock_create_file, mock_async_database_session, mock_message_with_voice):
        """Test extracting voice message with transcription."""

        # Mock transcription
        with patch("areyouok_telegram.handlers.utils.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = "[Transcribed Audio] Test transcription"

            result = await extract_media_from_telegram_message(mock_async_database_session, mock_message_with_voice)

        # Should process voice and transcription
        assert result == 2  # Voice file + transcription
        assert mock_create_file.call_count == 2

        # Verify voice file was saved
        first_call = mock_create_file.call_args_list[0]
        assert first_call.kwargs["file_id"] == "voice_test_123"
        assert first_call.kwargs["content_bytes"] == b"fake_voice_data"

        # Verify transcription was saved
        second_call = mock_create_file.call_args_list[1]
        assert second_call.kwargs["file_id"] == "voice_test_123_transcription"
        assert second_call.kwargs["content_bytes"] == b"[Transcribed Audio] Test transcription"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.MediaFiles.create_file")
    async def test_extract_voice_transcription_error(
        self, mock_create_file, mock_async_database_session, mock_message_with_voice
    ):
        """Test voice extraction when transcription fails."""
        # Mock transcription to fail
        with patch("areyouok_telegram.handlers.utils.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = VoiceNotProcessableError()

            result = await extract_media_from_telegram_message(mock_async_database_session, mock_message_with_voice)

        # Should still save voice file even if transcription fails
        assert result == 1  # Only voice file
        assert mock_create_file.call_count == 1

        # Verify only voice file was saved
        call_kwargs = mock_create_file.call_args.kwargs
        assert call_kwargs["file_id"] == "voice_test_123"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.MediaFiles.create_file")
    async def test_extract_multiple_media_types(
        self, mock_create_file, mock_async_database_session, mock_message_with_photo, mock_document
    ):
        """Test extracting multiple media types from a message."""
        # Modify the photo message to also have a document
        mock_message_with_photo.document = mock_document

        result = await extract_media_from_telegram_message(mock_async_database_session, mock_message_with_photo)

        # Should process both photo and document
        assert result == 2
        assert mock_create_file.call_count == 2
