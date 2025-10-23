import asyncio
import time
from datetime import UTC, datetime
from io import BytesIO

import logfire
import openai
import telegram
from openai.types import audio as openai_audio
from pydub import AudioSegment

from areyouok_telegram.config import OPENAI_API_KEY
from areyouok_telegram.data.models import Chat, LLMUsage, MediaFile, Notification
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import telegram_call


class VoiceNotProcessableError(Exception):
    """Raised when voice cannot be processed."""

    def __init__(self) -> None:
        message: str = "Voice message could not be processed."
        super().__init__(message)


@traced(extract_args=["message"])
async def extract_media_from_telegram_message(
    chat: Chat,
    *,
    message: telegram.Message,
    session_id: int | None = None,
) -> int:
    """Process media files from a Telegram message.

    Args:
        chat: Chat object
        message: Telegram message object
        session_id: Optional session ID

    Returns:
        int: Number of media files processed
    """
    get_file_coros = []

    if message.photo:
        get_file_coros.append(telegram_call(message.photo[-1].get_file))
    if message.sticker:
        get_file_coros.append(telegram_call(message.sticker.get_file))
    if message.document:
        get_file_coros.append(telegram_call(message.document.get_file))
    if message.animation:
        get_file_coros.append(telegram_call(message.animation.get_file))
    if message.video:
        get_file_coros.append(telegram_call(message.video.get_file))
    if message.video_note:
        get_file_coros.append(telegram_call(message.video_note.get_file))
    if message.voice:
        get_file_coros.append(telegram_call(message.voice.get_file))

    media_files = await asyncio.gather(*get_file_coros)

    await asyncio.gather(
        *[
            _download_file(
                chat,
                session_id=session_id,
                message=message,
                file=file,
            )
            for file in media_files
        ],
        return_exceptions=True,
    )

    logfire.info(
        f"Processed {len(media_files)} media files from message.",
        message_id=message.message_id,
        chat_id=message.chat.id,
        processed_count=len(media_files),
    )

    return len(media_files)


@traced(extract_args=["chat_id", "message_id"])
async def handle_unsupported_media(
    *,
    chat_id: int,
    message_id: int,
) -> None:
    """Check for unsupported media types and create notifications.

    Args:
        chat_id: Chat ID (internal ID)
        message_id: Message ID (internal ID)
    """
    chat = await Chat.get_by_id(chat_id=chat_id)
    if not chat:
        return

    stored_media = await MediaFile.get_by_message(
        chat=chat,
        message_id=message_id,
    )

    if stored_media:
        # Find unsupported media types (excluding audio files)
        unsupported_media = [m for m in stored_media if not m.is_openai_google_supported]
        unsupported_media_types = [m.mime_type for m in unsupported_media]

        if unsupported_media_types:
            # Create notification for unsupported media
            if len(unsupported_media_types) == 1:
                content = f"The user sent a {unsupported_media_types[0]} file, but you can only view images and PDFs."
            else:
                content = (
                    f"The user sent {', '.join(unsupported_media_types)} files, but you can only view images and PDFs."
                )

            notification = Notification(
                chat_id=chat_id,
                content=content,
                priority=2,
            )
            await notification.save()


@traced(extract_args=["message", "file"])
async def _download_file(
    chat: Chat,
    *,
    message: telegram.Message,
    file: telegram.File,
    session_id: int | None = None,
) -> bytes:
    """Download a Telegram file as bytes.

    Args:
        chat: Chat object (provides context and encryption key)
        message: Telegram message object
        file: Telegram file
        session_id: Optional session ID
    """
    try:
        content_bytes = await telegram_call(file.download_as_bytearray)

        # Create and save media file
        media_file = MediaFile(
            chat=chat,
            message_id=message.message_id,
            file_id=file.file_id,
            file_unique_id=file.file_unique_id,
            mime_type=file.file_path.split(".")[-1] if file.file_path else "application/octet-stream",
            bytes_data=bytes(content_bytes),
            file_size=file.file_size,
        )
        await media_file.save()

        # For voice messages, also create a transcription
        if message.voice and file.file_unique_id == message.voice.file_unique_id:
            with logfire.span(
                "Transcribing voice message",
                _span_name="handlers.utils._download_file.transcribe_voice",
                chat_id=message.chat.id,
                message_id=message.message_id,
                file_id=file.file_id,
                file_unique_id=file.file_unique_id,
            ):
                try:
                    # Transcribe the voice message in a separate thread
                    start_time = time.perf_counter()

                    transcriptions = await asyncio.to_thread(transcribe_voice_data_sync, bytes(content_bytes))
                    transcription_text = "[Transcribed Audio] " + " ".join([t.text for t in transcriptions if t.text])

                    end_time = time.perf_counter()

                    llm_usage = LLMUsage(
                        chat_id=chat.id,
                        session_id=session_id,
                        timestamp=datetime.now(UTC),
                        usage_type="openai.voice_transcription",
                        model="gpt-4o-transcribe",
                        provider="openai",
                        input_tokens=sum(t.usage.prompt_tokens for t in transcriptions),
                        output_tokens=sum(t.usage.completion_tokens for t in transcriptions),
                        runtime=end_time - start_time,
                    )
                    await llm_usage.save()

                    # Store the transcription as a text file
                    transcription_bytes = transcription_text.encode("utf-8")
                    transcription_media = MediaFile(
                        chat=chat,
                        message_id=message.message_id,
                        file_id=f"{file.file_id}_transcription",
                        file_unique_id=f"{file.file_unique_id}_transcription",
                        mime_type="text/plain",
                        bytes_data=transcription_bytes,
                        file_size=len(transcription_bytes),
                    )
                    await transcription_media.save()
                    logfire.info(
                        f"Transcription is {len(transcription_text)} characters long.", chat_id=message.chat.id
                    )

                except VoiceNotProcessableError:
                    logfire.exception(
                        "Voice message could not be transcribed.",
                        chat_id=message.chat.id,
                        message_id=message.message_id,
                        file_id=file.file_id,
                        file_unique_id=file.file_unique_id,
                    )

    except Exception as e:
        logfire.exception(
            "Failed to download file.",
            _exc_info=e,
            chat_id=message.chat.id,
            message_id=message.message_id,
            file_id=file.file_id,
            file_unique_id=file.file_unique_id,
        )


def transcribe_voice_data_sync(voice_data: bytes) -> list[openai_audio.transcription.Transcription]:
    """Synchronously transcribe voice data using OpenAI.

    Args:
        voice_data: Voice file content as bytes

    Returns:
        Transcribed text

    Raises:
        VoiceNotProcessableError: If voice cannot be processed
    """
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    try:
        audio_segment = AudioSegment.from_ogg(BytesIO(voice_data))

        max_segment_length = 10 * 60 * 1000  # 10 minutes in milliseconds
        total_duration = len(audio_segment)
        transcriptions = []

        start = 0
        while start < total_duration:
            end = min(start + max_segment_length, total_duration)
            segment = audio_segment[start:end]

            # Export segment to mp3 format for OpenAI
            audio_file = BytesIO()
            segment.export(audio_file, format="mp3")
            audio_file.seek(0)
            audio_file.name = "segment.mp3"

            transcription = client.audio.transcriptions.create(
                file=audio_file,
                model="gpt-4o-transcribe",
                chunking_strategy="auto",
                language="en",
                prompt=transcriptions[-1].text
                if transcriptions and getattr(transcriptions[-1], "text", None)
                else None,
                temperature=0.2,
            )
            transcriptions.append(transcription)
            start = end

    except Exception as e:
        raise VoiceNotProcessableError() from e

    return transcriptions
