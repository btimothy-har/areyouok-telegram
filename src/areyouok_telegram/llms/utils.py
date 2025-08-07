# ruff: noqa: TRY003

import json
from datetime import UTC
from datetime import datetime

import logfire
import pydantic_ai
import telegram
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider

from areyouok_telegram.config import ENV
from areyouok_telegram.config import OPENROUTER_API_KEY
from areyouok_telegram.data import Context
from areyouok_telegram.data import LLMUsage
from areyouok_telegram.data import MediaFiles
from areyouok_telegram.data import MessageTypes
from areyouok_telegram.data import async_database

pydantic_ai_instrumentation = InstrumentationSettings(include_content=True if ENV == "research" else False)

openrouter_provider = OpenRouterProvider(api_key=OPENROUTER_API_KEY)


async def run_agent_with_tracking(
    agent: pydantic_ai.Agent,
    *,
    chat_id: str,
    session_id: str,
    run_kwargs: dict,
) -> pydantic_ai.agent.AgentRunResult:
    """
    Run a Pydantic AI agent and automatically track its usage.

    Args:
        agent: The Pydantic AI agent to run
        chat_id: The chat ID for tracking
        session_id: The session ID for tracking
        run_kwargs: Arguments to pass to agent.run()

    Returns:
        The agent run result
    """

    # Ensure required kwargs are present
    if "user_prompt" not in run_kwargs and "message_history" not in run_kwargs:
        raise ValueError("Either 'user_prompt' or 'message_history' must be provided in run_kwargs")

    result = await agent.run(**run_kwargs)

    try:
        # Always track llm usage in a separate async context
        async with async_database() as db_conn:
            await LLMUsage.track_pydantic_usage(
                db_conn=db_conn,
                chat_id=chat_id,
                session_id=session_id,
                agent=agent,
                data=result.usage(),
            )
    except Exception as e:
        # Log the error but don't raise it, as we want to return the result regardless
        logfire.exception(
            f"Failed to log LLM usage: {e}",
            agent=agent.name,
            chat_id=chat_id,
            session_id=session_id,
        )

    return result


def telegram_message_to_dict(message: MessageTypes, ts_reference: datetime | None = None) -> dict:
    """
    Convert a Telegram message to a simplified dictionary format for LLM processing.

    Args:
        message: The Telegram message object.
        ts_reference: A datetime object to reference the timestamp against.

    Returns:
        A dictionary containing the message text, message ID, and timestamp.
    """

    ts_reference = ts_reference or datetime.now(UTC)

    if isinstance(message, telegram.Message):
        return {
            "text": message.text or message.caption or "",
            "message_id": str(message.message_id),
            "timestamp": f"{int((ts_reference - message.date).total_seconds())} seconds ago",
        }

    elif isinstance(message, telegram.MessageReactionUpdated):
        # Handle reactions, assuming only emoji reactions for simplicity
        # TODO: Handle custom and paid reactions
        reaction_string = ", ".join([
            r.emoji for r in message.new_reaction if r.type == telegram.constants.ReactionType.EMOJI
        ])
        return {
            "reaction": reaction_string,
            "to_message_id": str(message.message_id),
            "timestamp": f"{int((ts_reference - message.date).total_seconds())} seconds ago",
        }

    else:
        raise TypeError(
            f"Unsupported message type: {type(message)}. Only Message and MessageReactionUpdated are supported."
        )


def context_to_model_message(
    context: Context, ts_reference: datetime | None = None
) -> pydantic_ai.messages.ModelResponse:
    ts_reference = ts_reference or datetime.now(UTC)

    model_message = pydantic_ai.messages.ModelResponse(
        parts=[
            pydantic_ai.messages.TextPart(
                content=json.dumps({
                    "timestamp": (f"{(ts_reference - context.created_at).total_seconds()} seconds ago"),
                    "content": f"Summary of prior conversation:\n\n{context.content}",
                }),
                part_kind="text",
            )
        ],
        timestamp=context.created_at,
        kind="response",
    )

    return model_message


def telegram_message_to_model_message(
    message: MessageTypes,
    media: list[MediaFiles],
    ts_reference: datetime | None = None,
    *,
    is_user: bool = False,
) -> pydantic_ai.messages.ModelMessage:
    """Helper function to convert a Telegram message/reaction to a model request or response."""
    ts_reference = ts_reference or datetime.now(UTC)

    if isinstance(message, telegram.MessageReactionUpdated):
        return _telegram_reaction_to_model_message(message, ts_reference, is_user=is_user)

    if isinstance(message, telegram.Message):
        return _telegram_message_to_model_message(message, media, ts_reference, is_user=is_user)


def _telegram_message_to_model_message(
    message: telegram.Message, media: list[MediaFiles], ts_reference: datetime, *, is_user: bool = False
) -> pydantic_ai.messages.ModelMessage:
    """Convert a Telegram message to a model request or response."""

    msg_dict = telegram_message_to_dict(message, ts_reference)

    if is_user:
        user_content = [json.dumps(msg_dict)]

        # Anthropic only supports images, PDFs and text files.
        compatible_media = [m for m in media if m.is_anthropic_supported]
        for m in compatible_media:
            if m.mime_type.startswith("image/") or m.mime_type == "application/pdf":
                user_content.append(
                    pydantic_ai.BinaryContent(
                        data=m.bytes_data,
                        media_type=m.mime_type,
                    )
                )
            elif m.mime_type.startswith("text/"):
                user_content.append(m.bytes_data.decode("utf-8"))

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


def _telegram_reaction_to_model_message(
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


async def get_unsupported_media_from_messages(
    db_conn, messages: list[telegram.Message], since_timestamp: datetime | None = None
) -> list[str]:
    """Get list of unsupported media types from messages

    Anthropic only supports images, PDFs and text files.
    We "soft pass" audio as we transcribe audio content before sending to the model.

    Args:
        db_conn: Database connection
        messages: List of telegram messages to check
        since_timestamp: Only check messages after this timestamp

    Returns:
        List of unsupported media type names (e.g., ["video/mp4"])
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
            db_conn, chat_id=str(message.chat.id), message_id=str(message.message_id)
        )

        for m in media_files:
            # Skip supported media types
            if (
                m.mime_type.startswith("image/")
                or m.mime_type == "application/pdf"
                or m.mime_type.startswith("text/")
                or m.mime_type.startswith("audio/")
            ):
                continue

            unsupported_media.append(m.mime_type)

    return unsupported_media
