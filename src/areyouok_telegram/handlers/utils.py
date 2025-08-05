import asyncio
from io import BytesIO

import openai
import telegram
from pydub import AudioSegment
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import OPENAI_API_KEY
from areyouok_telegram.data import MediaFiles


class VoiceNotProcessableError(Exception):
    """Raised when voice cannot be processed."""

    pass


def transcribe_voice_data_sync(voice_data: bytes) -> str:
    """Synchronously transcribe voice data using OpenAI Whisper.

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
                model="gpt-4o-transcribe",
                file=audio_file,
                response_format="text",
                language="en",
                prompt=transcriptions[-1] if transcriptions else None,
                temperature=0.0,
            )
            transcriptions.append(transcription)
            start = end

        return "[Transcribed Audio] " + " ".join(transcriptions)

    except Exception as e:
        raise VoiceNotProcessableError() from e


async def extract_media_from_telegram_message(
    session: AsyncSession,
    message: telegram.Message,
) -> int:
    """Process media files from a Telegram message.

    Args:
        session: Database session
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

    processed_count = 0
    for file in media_files:
        # Download file content as bytes
        content_bytes = await file.download_as_bytearray()

        # Pass individual attributes to create_file
        await MediaFiles.create_file(
            session=session,
            file_id=file.file_id,
            file_unique_id=file.file_unique_id,
            chat_id=str(message.chat.id),
            message_id=str(message.id),
            file_size=file.file_size,
            content_bytes=bytes(content_bytes),
        )
        processed_count += 1

        # For voice messages, also create a transcription
        if message.voice and file.file_unique_id == message.voice.file_unique_id:
            try:
                # Transcribe the voice message in a separate thread
                transcription = await asyncio.to_thread(transcribe_voice_data_sync, bytes(content_bytes))

                # Store the transcription as a text file
                transcription_bytes = transcription.encode("utf-8")
                await MediaFiles.create_file(
                    session=session,
                    file_id=f"{file.file_id}_transcription",
                    file_unique_id=f"{file.file_unique_id}_transcription",
                    chat_id=str(message.chat.id),
                    message_id=str(message.id),
                    file_size=len(transcription_bytes),
                    content_bytes=transcription_bytes,
                )
                processed_count += 1
            except VoiceNotProcessableError:
                # If transcription fails, we still have the original voice file
                pass

    return processed_count
