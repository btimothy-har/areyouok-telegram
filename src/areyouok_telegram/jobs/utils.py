import json
from datetime import UTC
from datetime import datetime

import pydantic_ai
import telegram

from areyouok_telegram.data import MediaFiles
from areyouok_telegram.data import MessageTypes
from areyouok_telegram.llms.utils import telegram_message_to_dict


async def convert_telegram_message_to_model_message(
    conn, message: MessageTypes, ts_reference: datetime | None = None, *, is_user: bool = False
) -> pydantic_ai.messages.ModelMessage:
    """Helper function to convert a Telegram message/reaction to a model request or response."""
    ts_reference = ts_reference or datetime.now(UTC)

    if isinstance(message, telegram.MessageReactionUpdated):
        return await _telegram_reaction_to_model_message(message, ts_reference, is_user=is_user)

    if isinstance(message, telegram.Message):
        return await _telegram_message_to_model_message(conn, message, ts_reference, is_user=is_user)


async def _telegram_message_to_model_message(
    conn, message: telegram.Message, ts_reference: datetime, *, is_user: bool = False
) -> pydantic_ai.messages.ModelMessage:
    """Convert a Telegram message to a model request or response."""
    media_files = await MediaFiles.get_by_message_id(
        conn, chat_id=str(message.chat.id), message_id=str(message.message_id)
    )
    msg_dict = telegram_message_to_dict(message, ts_reference)

    if is_user:
        user_content = [json.dumps(msg_dict)]

        for m in media_files:
            if m.mime_type.startswith("image/") or m.mime_type == "application/pdf":
                user_content.append(
                    pydantic_ai.BinaryContent(
                        data=m.bytes_data,
                        media_type=m.mime_type,
                    )
                )
            elif m.mime_type.startswith("text/"):
                user_content.append(m.bytes_data.decode("utf-8"))
            # Don't include unsupported media types in content

        model_message = pydantic_ai.messages.ModelRequest(
            parts=[
                pydantic_ai.messages.UserPromptPart(
                    content=user_content if len(user_content) > 1 else user_content[0],
                    timestamp=message.date,
                    part_kind="user-prompt",
                )
            ],
            kind="request",
        )
    else:
        model_message = pydantic_ai.messages.ModelResponse(
            parts=[pydantic_ai.messages.TextPart(content=json.dumps(msg_dict), part_kind="text")],
            timestamp=message.date,
            kind="response",
        )

    return model_message


async def get_unsupported_media_from_messages(
    conn, messages: list[telegram.Message], since_timestamp: datetime | None = None
) -> list[str]:
    """Get list of unsupported media types from messages.

    Args:
        conn: Database connection
        messages: List of telegram messages to check
        since_timestamp: Only check messages after this timestamp

    Returns:
        List of unsupported media type names (e.g., ["video", "audio"])
    """
    unsupported_media = []

    for message in messages:
        # Skip messages before the timestamp if provided
        if since_timestamp and message.date <= since_timestamp:
            continue

        # Only check user messages
        if not message.from_user:
            continue

        media_files = await MediaFiles.get_by_message_id(
            conn, chat_id=str(message.chat.id), message_id=str(message.message_id)
        )

        for m in media_files:
            # Skip supported media types
            if m.mime_type.startswith("image/") or m.mime_type == "application/pdf":
                continue
            elif m.mime_type.startswith("text/"):
                continue

            # Track unsupported media types
            if m.mime_type.startswith("video/"):
                unsupported_media.append("video")
            elif m.mime_type.startswith("audio/"):
                unsupported_media.append("audio")
            else:
                unsupported_media.append(m.mime_type)

    return unsupported_media


async def _telegram_reaction_to_model_message(
    reaction: telegram.MessageReactionUpdated, ts_reference: datetime, *, is_user: bool = False
) -> pydantic_ai.messages.ModelMessage:
    """Convert a Telegram message reaction to a model request or response."""

    msg_dict = telegram_message_to_dict(reaction, ts_reference)

    if is_user:
        return pydantic_ai.messages.ModelRequest(
            parts=[
                pydantic_ai.messages.UserPromptPart(
                    content=json.dumps(msg_dict),
                    timestamp=reaction.date,
                    part_kind="user-prompt",
                )
            ],
            kind="request",
        )
    else:
        return pydantic_ai.messages.ModelResponse(
            parts=[pydantic_ai.messages.TextPart(content=json.dumps(msg_dict), part_kind="text")],
            timestamp=reaction.date,
            kind="response",
        )
