"""Tests for handlers/media.py."""

# ruff: noqa: PLC2701
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram
from pydub import AudioSegment

from areyouok_telegram.handlers.utils.media import (
    VoiceNotProcessableError,
    _download_file,
    extract_media_from_telegram_message,
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


