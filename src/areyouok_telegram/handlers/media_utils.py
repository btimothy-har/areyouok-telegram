import asyncio
from io import BytesIO

import logfire
import openai
import telegram
from openai.types import audio as openai_audio
from pydub import AudioSegment
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import OPENAI_API_KEY
from areyouok_telegram.data import LLMUsage
from areyouok_telegram.data import MediaFiles
from areyouok_telegram.handlers.exceptions import VoiceNotProcessableError
from areyouok_telegram.utils import telegram_retry
from areyouok_telegram.utils import traced


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
                prompt=transcriptions[-1] if transcriptions else None,
                temperature=0.2,
            )
            transcriptions.append(transcription)
            start = end

    except Exception as e:
        raise VoiceNotProcessableError() from e

    return transcriptions


@traced(extract_args=["message", "file"])
async def _download_file(
    db_conn: AsyncSession,
    user_encryption_key: str,
    *,
    message: telegram.Message,
    file: telegram.File,
    session_id: str | None = None,
) -> bytes:
    """Download a Telegram file as bytes.

    Args:
        db_conn: Database connection
        user_encryption_key: The user's Fernet encryption key
        message: Telegram message object
        file: Telegram file
    """
    try:
        content_bytes = await file.download_as_bytearray()

        # Pass individual attributes to create_file
        await MediaFiles.create_file(
            db_conn,
            user_encryption_key,
            file_id=file.file_id,
            file_unique_id=file.file_unique_id,
            chat_id=str(message.chat.id),
            message_id=str(message.id),
            file_size=file.file_size,
            content_bytes=bytes(content_bytes),
        )

        # For voice messages, also create a transcription
        if message.voice and file.file_unique_id == message.voice.file_unique_id:
            with logfire.span(
                "Transcribing voice message",
                _span_name="handlers.utils._download_file.transcribe_voice",
                chat_id=message.chat.id,
                message_id=message.id,
                file_id=file.file_id,
                file_unique_id=file.file_unique_id,
            ):
                try:
                    # Transcribe the voice message in a separate thread
                    transcriptions = await asyncio.to_thread(transcribe_voice_data_sync, bytes(content_bytes))
                    transcription_text = "[Transcribed Audio] " + " ".join([t.text for t in transcriptions if t.text])

                    await LLMUsage.track_generic_usage(
                        db_conn,
                        chat_id=str(message.chat.id),
                        session_id=session_id,
                        usage_type="openai.voice_transcription",
                        model="openai/gpt-4o-transcribe",
                        provider="openai",
                        input_tokens=sum(t.usage.input_tokens for t in transcriptions),
                        output_tokens=sum(t.usage.output_tokens for t in transcriptions),
                    )

                    # Store the transcription as a text file
                    transcription_bytes = transcription_text.encode("utf-8")
                    await MediaFiles.create_file(
                        db_conn,
                        user_encryption_key,
                        file_id=f"{file.file_id}_transcription",
                        file_unique_id=f"{file.file_unique_id}_transcription",
                        chat_id=str(message.chat.id),
                        message_id=str(message.id),
                        file_size=len(transcription_bytes),
                        content_bytes=transcription_bytes,
                    )
                    logfire.info(
                        f"Transcription is {len(transcription_text)} characters long.", chat_id=message.chat.id
                    )

                except VoiceNotProcessableError:
                    logfire.exception(
                        "Voice message could not be transcribed.",
                        chat_id=message.chat.id,
                        message_id=message.id,
                        file_id=file.file_id,
                        file_unique_id=file.file_unique_id,
                    )

    except Exception as e:
        logfire.exception(
            "Failed to download file.",
            exc_info=e,
            chat_id=message.chat.id,
            message_id=message.id,
            file_id=file.file_id,
            file_unique_id=file.file_unique_id,
        )


@traced(extract_args=["message"])
@telegram_retry()
async def extract_media_from_telegram_message(
    db_conn: AsyncSession,
    user_encryption_key: str,
    *,
    message: telegram.Message,
    session_id: str | None = None,
) -> int:
    """Process media files from a Telegram message.

    Args:
        db_conn: Database connection
        user_encryption_key: The user's Fernet encryption key
        message: Telegram message object

    Returns:
        int: Number of media files processed
    """
    media_files = []

    if message.photo:
        photo_file = await message.photo[-1].get_file()
        media_files.append(photo_file)

    if message.sticker:
        sticker_file = await message.sticker.get_file()
        media_files.append(sticker_file)

    if message.document:
        document_file = await message.document.get_file()
        media_files.append(document_file)

    if message.animation:
        animation_file = await message.animation.get_file()
        media_files.append(animation_file)

    if message.video:
        video_file = await message.video.get_file()
        media_files.append(video_file)

    if message.video_note:
        video_note_file = await message.video_note.get_file()
        media_files.append(video_note_file)

    if message.voice:
        voice_file = await message.voice.get_file()
        media_files.append(voice_file)

    await asyncio.gather(
        *[
            _download_file(
                db_conn,
                user_encryption_key,
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
