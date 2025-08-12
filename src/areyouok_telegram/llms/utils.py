# ruff: noqa: TRY003

import json
from datetime import UTC
from datetime import datetime

import logfire
import pydantic_ai
import telegram

from areyouok_telegram.data import Context
from areyouok_telegram.data import LLMUsage
from areyouok_telegram.data import MediaFiles
from areyouok_telegram.data import Messages
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.exceptions import MessageAlreadyDeletedError


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


def message_to_dict(message: Messages, ts_reference: datetime | None = None) -> dict:
    """
    Convert a Telegram message to a simplified dictionary format for LLM processing.

    Args:
        message: The Telegram message object.
        ts_reference: A datetime object to reference the timestamp against.

    Returns:
        A dictionary containing the message text, message ID, and timestamp.
    """

    ts_reference = ts_reference or datetime.now(UTC)

    if message.message_type == "Message":
        payload = {
            "text": message.telegram_object.text or message.telegram_object.caption or "",
            "message_id": str(message.message_id),
            "timestamp": f"{int((ts_reference - message.telegram_object.date).total_seconds())} seconds ago",
        }

    elif isinstance(message, telegram.MessageReactionUpdated):
        # Handle reactions, assuming only emoji reactions for simplicity
        # TODO: Handle custom and paid reactions
        reaction_string = ", ".join(
            [r.emoji for r in message.telegram_object.new_reaction if r.type == telegram.constants.ReactionType.EMOJI]
        )
        payload = {
            "reaction": reaction_string,
            "to_message_id": str(message.message_id),
            "timestamp": f"{int((ts_reference - message.telegram_object.date).total_seconds())} seconds ago",
        }

    else:
        raise TypeError(
            f"Unsupported message type: {type(message)}. Only Message and MessageReactionUpdated are supported."
        )

    if message.reasoning:
        payload["reasoning"] = message.reasoning

    return payload


def context_to_model_message(
    context: Context, ts_reference: datetime | None = None
) -> pydantic_ai.messages.ModelResponse:
    ts_reference = ts_reference or datetime.now(UTC)

    model_message = pydantic_ai.messages.ModelResponse(
        parts=[
            pydantic_ai.messages.TextPart(
                content=json.dumps(
                    {
                        "timestamp": (f"{(ts_reference - context.created_at).total_seconds()} seconds ago"),
                        "content": f"Summary of prior conversation:\n\n{context.content}",
                    }
                ),
                part_kind="text",
            )
        ],
        timestamp=context.created_at,
        kind="response",
    )

    return model_message


def message_to_model_message(
    message: Messages,
    media: list[MediaFiles],
    ts_reference: datetime | None = None,
    *,
    is_user: bool = False,
) -> pydantic_ai.messages.ModelMessage:
    """Helper function to convert a Messages SQLAlchemy object to a model request or response.

    Note: The message must have its payload decrypted before calling this function.
    """

    # Check if message is soft-deleted
    telegram_obj = message.telegram_object  # Will raise ContentNotDecryptedError if not decrypted
    if telegram_obj is None:
        raise MessageAlreadyDeletedError(message.message_id)

    ts_reference = ts_reference or datetime.now(UTC)

    if message.message_type == "MessageReactionUpdated":
        return _reaction_to_model_message(message, ts_reference, is_user=is_user)
    elif message.message_type == "Message":
        return _message_to_model_message(message, media, ts_reference, is_user=is_user)
    else:
        raise TypeError(f"Unsupported message type: {message.message_type}")


def _message_to_model_message(
    message: Messages, media: list[MediaFiles], ts_reference: datetime, *, is_user: bool = False
) -> pydantic_ai.messages.ModelMessage:
    """Convert a Messages SQLAlchemy object to a model request or response."""

    msg_dict = message_to_dict(message, ts_reference)

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
                    timestamp=message.telegram_object.date,
                    part_kind="user-prompt",
                )
            ],
            kind="request",
        )
    else:
        model_message = pydantic_ai.messages.ModelResponse(
            parts=[pydantic_ai.messages.TextPart(content=json.dumps(msg_dict), part_kind="text")],
            timestamp=message.telegram_object.date,
            kind="response",
        )

    return model_message


def _reaction_to_model_message(
    message: "Messages", ts_reference: datetime, *, is_user: bool = False
) -> pydantic_ai.messages.ModelMessage:
    """Convert a Messages SQLAlchemy object (reaction type) to a model request or response."""

    msg_dict = message_to_dict(message, ts_reference)

    if is_user:
        return pydantic_ai.messages.ModelRequest(
            parts=[
                pydantic_ai.messages.UserPromptPart(
                    content=json.dumps(msg_dict),
                    timestamp=message.telegram_object.date,
                    part_kind="user-prompt",
                )
            ],
            kind="request",
        )
    else:
        return pydantic_ai.messages.ModelResponse(
            parts=[pydantic_ai.messages.TextPart(content=json.dumps(msg_dict), part_kind="text")],
            timestamp=message.telegram_object.date,
            kind="response",
        )
