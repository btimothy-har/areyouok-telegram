"""Tests for utils/media.py."""

# ruff: noqa: PLC2701
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram
from pydub import AudioSegment

from areyouok_telegram.utils.media import (
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
            patch("areyouok_telegram.utils.media.AudioSegment.from_ogg", return_value=mock_audio_segment),
            patch("areyouok_telegram.utils.media.openai.OpenAI", return_value=mock_client),
            patch("areyouok_telegram.utils.media.OPENAI_API_KEY", "test-key"),
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
            patch("areyouok_telegram.utils.media.AudioSegment.from_ogg", return_value=mock_audio_segment),
            patch("areyouok_telegram.utils.media.openai.OpenAI", return_value=mock_client),
            patch("areyouok_telegram.utils.media.OPENAI_API_KEY", "test-key"),
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
            "areyouok_telegram.utils.media.AudioSegment.from_ogg",
            side_effect=Exception("Audio processing error"),
        ):
            with pytest.raises(VoiceNotProcessableError):
                transcribe_voice_data_sync(mock_voice_data)


class TestDownloadFile:
    """Test the _download_file function."""

    @pytest.mark.asyncio
    async def test_download_file_non_voice(self, mock_db_session):
        """Test downloading a non-voice file."""
        # Create mock message and file
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.chat.id = 123
        mock_message.id = 456
        mock_message.message_id = 456  # Both aliases should return the same value
        mock_message.voice = None  # Not a voice message

        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_id = "file123"
        mock_file.file_unique_id = "unique123"
        mock_file.file_size = 1024
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"file content"))

        chat_encryption_key = "test_encryption_key"

        with (
            patch("areyouok_telegram.utils.media.MediaFiles.create_file", new=AsyncMock()) as mock_create_file,
            patch("areyouok_telegram.utils.media.logfire.span"),
            patch("areyouok_telegram.utils.media.logfire.info"),
        ):
            await _download_file(mock_db_session, chat_encryption_key, message=mock_message, file=mock_file)

            # Verify file was downloaded
            mock_file.download_as_bytearray.assert_called_once()

            # Verify file was saved to database
            mock_create_file.assert_called_once_with(
                mock_db_session,
                chat_encryption_key,
                file_id="file123",
                file_unique_id="unique123",
                chat_id="123",
                message_id="456",
                file_size=1024,
                content_bytes=b"file content",
            )

    @pytest.mark.asyncio
    async def test_download_voice_file_with_transcription(self, mock_db_session):
        """Test downloading a voice file with successful transcription."""
        # Create mock message with voice
        mock_voice = MagicMock()
        mock_voice.file_unique_id = "voice_unique123"

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.chat.id = 123
        mock_message.id = 456
        mock_message.voice = mock_voice

        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_id = "voice123"
        mock_file.file_unique_id = "voice_unique123"
        mock_file.file_size = 2048
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"voice content"))

        # Create mock transcription objects
        mock_transcription = MagicMock()
        mock_transcription.text = "Hello world"
        mock_transcription.usage.prompt_tokens = 10
        mock_transcription.usage.completion_tokens = 5
        mock_transcriptions = [mock_transcription]

        chat_encryption_key = "test_encryption_key"

        with (
            patch("areyouok_telegram.utils.media.MediaFiles.create_file", new=AsyncMock()) as mock_create_file,
            patch(
                "areyouok_telegram.utils.media.asyncio.to_thread",
                new=AsyncMock(return_value=mock_transcriptions),
            ),
            patch("areyouok_telegram.utils.media.LLMUsage.track_generic_usage", new=AsyncMock()) as mock_track_usage,
            patch("areyouok_telegram.utils.media.logfire.span"),
            patch("areyouok_telegram.utils.media.logfire.info") as mock_log_info,
        ):
            await _download_file(mock_db_session, chat_encryption_key, message=mock_message, file=mock_file)

            # Verify file was downloaded
            mock_file.download_as_bytearray.assert_called_once()

            # Verify both voice file and transcription were saved
            assert mock_create_file.call_count == 2

            # First call saves the voice file (positional args: db_conn, chat_encryption_key, then kwargs)
            first_call = mock_create_file.call_args_list[0]
            assert first_call[0][0] == mock_db_session  # db_conn
            assert first_call[0][1] == chat_encryption_key  # chat_encryption_key
            assert first_call[1]["file_id"] == "voice123"
            assert first_call[1]["content_bytes"] == b"voice content"

            # Second call saves the transcription
            second_call = mock_create_file.call_args_list[1]
            assert second_call[0][0] == mock_db_session  # db_conn
            assert second_call[0][1] == chat_encryption_key  # chat_encryption_key
            assert second_call[1]["file_id"] == "voice123_transcription"
            assert second_call[1]["file_unique_id"] == "voice_unique123_transcription"
            transcription_text = "[Transcribed Audio] Hello world"
            assert second_call[1]["content_bytes"] == transcription_text.encode("utf-8")

            # Verify LLM usage was tracked
            mock_track_usage.assert_called_once_with(
                mock_db_session,
                chat_id="123",
                session_id=None,
                usage_type="openai.voice_transcription",
                model="openai/gpt-4o-transcribe",
                provider="openai",
                input_tokens=10,
                output_tokens=5,
                runtime=0.0,
            )

            # Verify logging
            mock_log_info.assert_called_with(
                f"Transcription is {len(transcription_text)} characters long.", chat_id=123
            )

    @pytest.mark.asyncio
    async def test_download_voice_file_transcription_error(self, mock_db_session):
        """Test downloading a voice file when transcription fails."""
        # Create mock message with voice
        mock_voice = MagicMock()
        mock_voice.file_unique_id = "voice_unique123"

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.chat.id = 123
        mock_message.id = 456
        mock_message.message_id = 456  # Both aliases should return the same value
        mock_message.voice = mock_voice

        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_id = "voice123"
        mock_file.file_unique_id = "voice_unique123"
        mock_file.file_size = 2048
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"voice content"))
        chat_encryption_key = "test_encryption_key"

        with (
            patch("areyouok_telegram.utils.media.MediaFiles.create_file", new=AsyncMock()) as mock_create_file,
            patch(
                "areyouok_telegram.utils.media.asyncio.to_thread",
                new=AsyncMock(side_effect=VoiceNotProcessableError()),
            ),
            patch("areyouok_telegram.utils.media.logfire.span"),
            patch("areyouok_telegram.utils.media.logfire.exception") as mock_log_exception,
        ):
            await _download_file(mock_db_session, chat_encryption_key, message=mock_message, file=mock_file)

            # Verify voice file was saved but transcription was not
            mock_create_file.assert_called_once_with(
                mock_db_session,
                chat_encryption_key,
                file_id="voice123",
                file_unique_id="voice_unique123",
                chat_id="123",
                message_id="456",
                file_size=2048,
                content_bytes=b"voice content",
            )

            # Verify error was logged
            mock_log_exception.assert_called_once_with(
                "Voice message could not be transcribed.",
                chat_id=123,
                message_id=456,
                file_id="voice123",
                file_unique_id="voice_unique123",
            )

    @pytest.mark.asyncio
    async def test_download_file_general_exception(self, mock_db_session):
        """Test handling general exceptions during file download."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.chat.id = 123
        mock_message.id = 456
        mock_message.voice = None

        mock_file = MagicMock(spec=telegram.File)
        mock_file.file_id = "file123"
        mock_file.file_unique_id = "unique123"
        mock_file.download_as_bytearray = AsyncMock(side_effect=Exception("Download failed"))

        chat_encryption_key = "test_encryption_key"

        with patch("areyouok_telegram.utils.media.logfire.exception") as mock_log_exception:
            await _download_file(mock_db_session, chat_encryption_key, message=mock_message, file=mock_file)

            # Verify error was logged
            mock_log_exception.assert_called_once()
            assert mock_log_exception.call_args[0][0] == "Failed to download file."


class TestExtractMediaFromTelegramMessage:
    """Test the extract_media_from_telegram_message function."""

    @pytest.mark.asyncio
    async def test_extract_no_media(self, mock_db_session):
        """Test extracting from message with no media."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.photo = None
        mock_message.sticker = None
        mock_message.document = None
        mock_message.animation = None
        mock_message.video = None
        mock_message.video_note = None
        mock_message.voice = None
        mock_message.message_id = 123
        mock_message.chat.id = 456

        with (
            patch("areyouok_telegram.utils.media._download_file", new=AsyncMock()) as mock_download,
            patch("areyouok_telegram.utils.media.logfire.info") as mock_log_info,
        ):
            result = await extract_media_from_telegram_message(
                mock_db_session, "test_encryption_key", message=mock_message
            )

            assert result == 0
            mock_download.assert_not_called()
            mock_log_info.assert_called_with(
                "Processed 0 media files from message.",
                message_id=123,
                chat_id=456,
                processed_count=0,
            )

    @pytest.mark.asyncio
    async def test_extract_photo(self, mock_db_session):
        """Test extracting photo from message."""
        mock_photo = MagicMock()
        mock_photo.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.photo = [mock_photo]  # Photo is a list
        mock_message.sticker = None
        mock_message.document = None
        mock_message.animation = None
        mock_message.video = None
        mock_message.video_note = None
        mock_message.voice = None
        mock_message.message_id = 123
        mock_message.chat.id = 456

        with (
            patch("areyouok_telegram.utils.media._download_file", new=AsyncMock()) as mock_download,
            patch("areyouok_telegram.utils.media.logfire.info") as mock_log_info,
        ):
            result = await extract_media_from_telegram_message(
                mock_db_session, "test_encryption_key", message=mock_message
            )

            assert result == 1
            mock_download.assert_called_once()
            mock_log_info.assert_called_with(
                "Processed 1 media files from message.",
                message_id=123,
                chat_id=456,
                processed_count=1,
            )

    @pytest.mark.asyncio
    async def test_extract_multiple_media_types(self, mock_db_session):
        """Test extracting multiple media types from message."""
        # Create mocks for different media types
        mock_photo = MagicMock()
        mock_photo.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_document = MagicMock()
        mock_document.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_voice = MagicMock()
        mock_voice.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.photo = [mock_photo]
        mock_message.sticker = None
        mock_message.document = mock_document
        mock_message.animation = None
        mock_message.video = None
        mock_message.video_note = None
        mock_message.voice = mock_voice
        mock_message.message_id = 123
        mock_message.chat.id = 456

        with (
            patch("areyouok_telegram.utils.media._download_file", new=AsyncMock()) as mock_download,
            patch("areyouok_telegram.utils.media.logfire.info") as mock_log_info,
        ):
            result = await extract_media_from_telegram_message(
                mock_db_session, "test_encryption_key", message=mock_message
            )

            assert result == 3
            assert mock_download.call_count == 3
            mock_log_info.assert_called_with(
                "Processed 3 media files from message.",
                message_id=123,
                chat_id=456,
                processed_count=3,
            )

    @pytest.mark.asyncio
    async def test_extract_all_media_types(self, mock_db_session):
        """Test extracting all supported media types."""
        # Create mocks for all media types
        mock_photo = MagicMock()
        mock_photo.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_sticker = MagicMock()
        mock_sticker.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_document = MagicMock()
        mock_document.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_animation = MagicMock()
        mock_animation.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_video = MagicMock()
        mock_video.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_video_note = MagicMock()
        mock_video_note.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_voice = MagicMock()
        mock_voice.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.photo = [mock_photo]
        mock_message.sticker = mock_sticker
        mock_message.document = mock_document
        mock_message.animation = mock_animation
        mock_message.video = mock_video
        mock_message.video_note = mock_video_note
        mock_message.voice = mock_voice
        mock_message.message_id = 123
        mock_message.chat.id = 456

        with (
            patch("areyouok_telegram.utils.media._download_file", new=AsyncMock()) as mock_download,
            patch("areyouok_telegram.utils.media.logfire.info") as mock_log_info,
        ):
            result = await extract_media_from_telegram_message(
                mock_db_session, "test_encryption_key", message=mock_message
            )

            assert result == 7
            assert mock_download.call_count == 7
            mock_log_info.assert_called_with(
                "Processed 7 media files from message.",
                message_id=123,
                chat_id=456,
                processed_count=7,
            )

    @pytest.mark.asyncio
    async def test_extract_media_with_download_exceptions(self, mock_db_session):
        """Test that download exceptions are handled gracefully."""
        mock_photo = MagicMock()
        mock_photo.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_document = MagicMock()
        mock_document.get_file = AsyncMock(return_value=MagicMock(spec=telegram.File))

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.photo = [mock_photo]
        mock_message.sticker = None
        mock_message.document = mock_document
        mock_message.animation = None
        mock_message.video = None
        mock_message.video_note = None
        mock_message.voice = None
        mock_message.message_id = 123
        mock_message.chat.id = 456

        # Mock one download to fail
        mock_download = AsyncMock(side_effect=[Exception("Download failed"), None])

        with (
            patch("areyouok_telegram.utils.media._download_file", mock_download),
            patch("areyouok_telegram.utils.media.logfire.info") as mock_log_info,
        ):
            result = await extract_media_from_telegram_message(
                mock_db_session, "test_encryption_key", message=mock_message
            )

            # Both files should be attempted, count is still 2
            assert result == 2
            assert mock_download.call_count == 2
            mock_log_info.assert_called_with(
                "Processed 2 media files from message.",
                message_id=123,
                chat_id=456,
                processed_count=2,
            )
