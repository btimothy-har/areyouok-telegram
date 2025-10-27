"""Tests for handlers/media.py."""

# ruff: noqa: PLC2701
from unittest.mock import MagicMock, patch

import pytest
import telegram
from pydub import AudioSegment

from areyouok_telegram.handlers.utils.media import (
    VoiceNotProcessableError,
    _get_mime_type_from_message,
    transcribe_voice_data_sync,
)


class TestTranscribeVoiceDataSync:
    """Test the transcribe_voice_data_sync function."""

    def test_transcribe_short_audio(self):
        """Test transcribing audio shorter than 10 minutes."""
        # Create mock audio data
        mock_voice_data = b"fake audio data"

        # Create a mock AudioSegment that's 5 minutes long
        mock_audio_segment = MagicMock(spec=AudioSegment)
        mock_audio_segment.__len__.return_value = 5 * 60 * 1000  # 5 minutes in milliseconds
        mock_audio_segment.__getitem__.return_value = mock_audio_segment
        mock_audio_segment.export = MagicMock()

        # Mock OpenAI client and transcription response
        mock_client = MagicMock()
        mock_transcription = MagicMock()
        mock_transcription.text = "This is a test transcription"
        mock_transcription.usage.prompt_tokens = 10
        mock_transcription.usage.completion_tokens = 5
        mock_client.audio.transcriptions.create.return_value = mock_transcription

        with (
            patch("areyouok_telegram.handlers.utils.media.AudioSegment.from_ogg", return_value=mock_audio_segment),
            patch("areyouok_telegram.handlers.utils.media.openai.OpenAI", return_value=mock_client),
            patch("areyouok_telegram.handlers.utils.media.OPENAI_API_KEY", "test-key"),
        ):
            result = transcribe_voice_data_sync(mock_voice_data)

            # Verify the result is a list of transcriptions
            assert len(result) == 1
            assert result[0].text == "This is a test transcription"

            # Verify AudioSegment was created from the voice data
            AudioSegment.from_ogg.assert_called_once()

            # Verify OpenAI transcription was called once (single segment)
            mock_client.audio.transcriptions.create.assert_called_once_with(
                file=mock_audio_segment.export.call_args[0][0],
                model="gpt-4o-transcribe",
                chunking_strategy="auto",
                language="en",
                prompt=None,
                temperature=0.2,
            )

    def test_transcribe_long_audio_multiple_segments(self):
        """Test transcribing audio longer than 10 minutes (multiple segments)."""
        mock_voice_data = b"fake audio data"

        # Create a mock AudioSegment that's 25 minutes long
        mock_audio_segment = MagicMock(spec=AudioSegment)
        mock_audio_segment.__len__.return_value = 25 * 60 * 1000  # 25 minutes in milliseconds
        mock_audio_segment.__getitem__.return_value = mock_audio_segment
        mock_audio_segment.export = MagicMock()

        # Mock OpenAI client with multiple transcription responses
        mock_client = MagicMock()
        mock_transcriptions = []
        for text in ["First segment", "Second segment", "Third segment"]:
            mock_transcription = MagicMock()
            mock_transcription.text = text
            mock_transcription.usage.input_tokens = 10
            mock_transcription.usage.output_tokens = 5
            mock_transcriptions.append(mock_transcription)
        mock_client.audio.transcriptions.create.side_effect = mock_transcriptions

        with (
            patch("areyouok_telegram.handlers.utils.media.AudioSegment.from_ogg", return_value=mock_audio_segment),
            patch("areyouok_telegram.handlers.utils.media.openai.OpenAI", return_value=mock_client),
            patch("areyouok_telegram.handlers.utils.media.OPENAI_API_KEY", "test-key"),
        ):
            result = transcribe_voice_data_sync(mock_voice_data)

            # Verify the result is a list of transcriptions
            assert len(result) == 3
            assert result[0].text == "First segment"
            assert result[1].text == "Second segment"
            assert result[2].text == "Third segment"

            # Verify OpenAI transcription was called 3 times (3 segments)
            assert mock_client.audio.transcriptions.create.call_count == 3

            # Verify the prompt for second and third segments uses previous transcription text
            calls = mock_client.audio.transcriptions.create.call_args_list
            assert calls[0][1]["prompt"] is None
            assert calls[1][1]["prompt"] == mock_transcriptions[0].text
            assert calls[2][1]["prompt"] == mock_transcriptions[1].text

    def test_transcribe_voice_data_sync_exception(self):
        """Test that exceptions are wrapped in VoiceNotProcessableError."""
        mock_voice_data = b"fake audio data"

        with patch(
            "areyouok_telegram.handlers.utils.media.AudioSegment.from_ogg",
            side_effect=Exception("Audio processing error"),
        ):
            with pytest.raises(VoiceNotProcessableError):
                transcribe_voice_data_sync(mock_voice_data)


class TestGetMimeTypeFromMessage:
    """Test the _get_mime_type_from_message function."""

    def test_document_with_mime_type(self):
        """Test extracting MIME type from Document."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_unique_id = "unique123"
        mock_file.file_path = "document.pdf"

        mock_document = MagicMock(spec=telegram.Document)
        mock_document.file_unique_id = "unique123"
        mock_document.mime_type = "application/pdf"

        mock_message.document = mock_document
        mock_message.video = None
        mock_message.audio = None
        mock_message.voice = None
        mock_message.sticker = None
        mock_message.animation = None
        mock_message.photo = None
        mock_message.video_note = None

        result = _get_mime_type_from_message(mock_message, mock_file)
        assert result == "application/pdf"

    def test_video_with_mime_type(self):
        """Test extracting MIME type from Video."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_unique_id = "unique456"
        mock_file.file_path = "video.mp4"

        mock_video = MagicMock(spec=telegram.Video)
        mock_video.file_unique_id = "unique456"
        mock_video.mime_type = "video/mp4"

        mock_message.document = None
        mock_message.video = mock_video
        mock_message.audio = None
        mock_message.voice = None
        mock_message.sticker = None
        mock_message.animation = None
        mock_message.photo = None
        mock_message.video_note = None

        result = _get_mime_type_from_message(mock_message, mock_file)
        assert result == "video/mp4"

    def test_audio_with_mime_type(self):
        """Test extracting MIME type from Audio."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_unique_id = "unique789"
        mock_file.file_path = "audio.mp3"

        mock_audio = MagicMock(spec=telegram.Audio)
        mock_audio.file_unique_id = "unique789"
        mock_audio.mime_type = "audio/mpeg"

        mock_message.document = None
        mock_message.video = None
        mock_message.audio = mock_audio
        mock_message.voice = None
        mock_message.sticker = None
        mock_message.animation = None
        mock_message.photo = None
        mock_message.video_note = None

        result = _get_mime_type_from_message(mock_message, mock_file)
        assert result == "audio/mpeg"

    def test_voice_with_mime_type(self):
        """Test extracting MIME type from Voice."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_unique_id = "unique101"
        mock_file.file_path = "voice.ogg"

        mock_voice = MagicMock(spec=telegram.Voice)
        mock_voice.file_unique_id = "unique101"
        mock_voice.mime_type = "audio/ogg"

        mock_message.document = None
        mock_message.video = None
        mock_message.audio = None
        mock_message.voice = mock_voice
        mock_message.sticker = None
        mock_message.animation = None
        mock_message.photo = None
        mock_message.video_note = None

        result = _get_mime_type_from_message(mock_message, mock_file)
        assert result == "audio/ogg"

    def test_sticker_returns_webp(self):
        """Test that stickers return image/webp."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_unique_id = "unique202"
        mock_file.file_path = "sticker.webp"

        mock_sticker = MagicMock(spec=telegram.Sticker)
        mock_sticker.file_unique_id = "unique202"

        mock_message.document = None
        mock_message.video = None
        mock_message.audio = None
        mock_message.voice = None
        mock_message.sticker = mock_sticker
        mock_message.animation = None
        mock_message.photo = None
        mock_message.video_note = None

        result = _get_mime_type_from_message(mock_message, mock_file)
        assert result == "image/webp"

    def test_animation_with_mime_type(self):
        """Test extracting MIME type from Animation."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_unique_id = "unique303"
        mock_file.file_path = "animation.gif"

        mock_animation = MagicMock(spec=telegram.Animation)
        mock_animation.file_unique_id = "unique303"
        mock_animation.mime_type = "image/gif"

        mock_message.document = None
        mock_message.video = None
        mock_message.audio = None
        mock_message.voice = None
        mock_message.sticker = None
        mock_message.animation = mock_animation
        mock_message.photo = None
        mock_message.video_note = None

        result = _get_mime_type_from_message(mock_message, mock_file)
        assert result == "image/gif"

    def test_photo_returns_jpeg(self):
        """Test that photos return image/jpeg."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_unique_id = "unique404"
        mock_file.file_path = "photo.jpg"

        mock_photo1 = MagicMock(spec=telegram.PhotoSize)
        mock_photo1.file_unique_id = "unique999"
        mock_photo2 = MagicMock(spec=telegram.PhotoSize)
        mock_photo2.file_unique_id = "unique404"

        mock_message.document = None
        mock_message.video = None
        mock_message.audio = None
        mock_message.voice = None
        mock_message.sticker = None
        mock_message.animation = None
        mock_message.photo = [mock_photo1, mock_photo2]
        mock_message.video_note = None

        result = _get_mime_type_from_message(mock_message, mock_file)
        assert result == "image/jpeg"

    def test_video_note_returns_mp4(self):
        """Test that video notes return video/mp4."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_unique_id = "unique505"
        mock_file.file_path = "video_note.mp4"

        mock_video_note = MagicMock(spec=telegram.VideoNote)
        mock_video_note.file_unique_id = "unique505"

        mock_message.document = None
        mock_message.video = None
        mock_message.audio = None
        mock_message.voice = None
        mock_message.sticker = None
        mock_message.animation = None
        mock_message.photo = None
        mock_message.video_note = mock_video_note

        result = _get_mime_type_from_message(mock_message, mock_file)
        assert result == "video/mp4"

    def test_fallback_to_mimetypes_guess(self):
        """Test fallback to mimetypes.guess_type when media type not found."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_unique_id = "unique606"
        mock_file.file_path = "file.png"

        mock_message.document = None
        mock_message.video = None
        mock_message.audio = None
        mock_message.voice = None
        mock_message.sticker = None
        mock_message.animation = None
        mock_message.photo = None
        mock_message.video_note = None

        result = _get_mime_type_from_message(mock_message, mock_file)
        assert result == "image/png"

    def test_fallback_to_octet_stream(self):
        """Test final fallback to application/octet-stream."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_unique_id = "unique707"
        mock_file.file_path = None  # No file path

        mock_message.document = None
        mock_message.video = None
        mock_message.audio = None
        mock_message.voice = None
        mock_message.sticker = None
        mock_message.animation = None
        mock_message.photo = None
        mock_message.video_note = None

        result = _get_mime_type_from_message(mock_message, mock_file)
        assert result == "application/octet-stream"

    def test_document_without_mime_type_uses_fallback(self):
        """Test that document without mime_type falls back to file path guessing."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_unique_id = "unique808"
        mock_file.file_path = "document.txt"

        mock_document = MagicMock(spec=telegram.Document)
        mock_document.file_unique_id = "unique808"
        mock_document.mime_type = None  # No MIME type provided

        mock_message.document = mock_document
        mock_message.video = None
        mock_message.audio = None
        mock_message.voice = None
        mock_message.sticker = None
        mock_message.animation = None
        mock_message.photo = None
        mock_message.video_note = None

        result = _get_mime_type_from_message(mock_message, mock_file)
        assert result == "text/plain"
