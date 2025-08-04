# ruff: noqa: TRY003

import json
from datetime import UTC
from datetime import datetime
from typing import Any
from typing import Dict

import dspy
import pydantic_ai
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import MessageTypes


def telegram_message_to_dict(message: MessageTypes, ts_reference) -> dict:
    """
    Convert a Telegram message to a simplified dictionary format for LLM processing.

    Args:
        message: The Telegram message object.
        ts_reference: A datetime object to reference the timestamp against.

    Returns:
        A dictionary containing the message text, message ID, and timestamp.
    """

    if isinstance(message, telegram.Message):
        return {
            "text": message.text,
            "message_id": str(message.message_id),
            "timestamp": f"{int((ts_reference - message.date).total_seconds())} seconds ago",
        }

    elif isinstance(message, telegram.MessageReactionUpdated):
        # Handle reactions, assuming only emoji reactions for simplicity
        # TODO: Handle custom and paid reactions
        reaction_string = ", ".join(
            [r.emoji for r in message.new_reaction if r.type == telegram.constants.ReactionType.EMOJI]
        )
        return {
            "reaction": reaction_string,
            "to_message_id": str(message.message_id),
            "timestamp": f"{int((ts_reference - message.date).total_seconds())} seconds ago",
        }

    else:
        raise TypeError(
            f"Unsupported message type: {type(message)}. Only Message and MessageReactionUpdated are supported."
        )


def convert_telegram_message_to_model_message(
    context: ContextTypes.DEFAULT_TYPE, message: MessageTypes, ts_reference: datetime | None = None
) -> pydantic_ai.messages.ModelMessage:
    """Helper function to convert a Telegram message/reaction to a model request or response."""
    ts_reference = ts_reference or datetime.now(UTC)

    if isinstance(message, telegram.MessageReactionUpdated):
        return _telegram_reaction_to_model_message(context, message, ts_reference)

    if isinstance(message, telegram.Message):
        return _telegram_message_to_model_message(context, message, ts_reference)


def _telegram_message_to_model_message(
    context: ContextTypes.DEFAULT_TYPE, message: telegram.Message, ts_reference: datetime
) -> pydantic_ai.messages.ModelMessage:
    """Convert a Telegram message to a model request or response."""

    msg_dict = telegram_message_to_dict(message, ts_reference)

    if message.from_user and message.from_user.id != context.bot.id:
        return pydantic_ai.messages.ModelRequest(
            parts=[
                pydantic_ai.messages.UserPromptPart(
                    content=json.dumps(msg_dict),
                    timestamp=message.date,
                    part_kind="user-prompt",
                )
            ],
            kind="request",
        )
    else:
        return pydantic_ai.messages.ModelResponse(
            parts=[pydantic_ai.messages.TextPart(content=json.dumps(msg_dict), part_kind="text")],
            timestamp=message.date,
            kind="response",
        )


def _telegram_reaction_to_model_message(
    context: ContextTypes.DEFAULT_TYPE, reaction: telegram.MessageReactionUpdated, ts_reference: datetime
) -> pydantic_ai.messages.ModelMessage:
    """Convert a Telegram message reaction to a model request or response."""

    msg_dict = telegram_message_to_dict(reaction, ts_reference)

    if reaction.user and reaction.user.id != context.bot.id:
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


def merge_dspy_usage_data(*predictions: dspy.Prediction) -> dict[str, Any]:
    """
    Merge LLM usage data from multiple dspy predictions.
    
    Args:
        *predictions: Variable number of dspy.Prediction objects
        
    Returns:
        Merged usage dictionary with accumulated token counts
    """
    total_usage = {}
    
    for pred in predictions:
        if hasattr(pred, "get_lm_usage"):
            usage = pred.get_lm_usage()
            if usage:
                _accumulate_usage(total_usage, usage)
    
    return total_usage


def _accumulate_usage(total: dict[str, Any], new: dict[str, Any]) -> None:
    """
    Accumulate usage data from new into total (in-place).
    
    Args:
        total: Dictionary to accumulate into (modified in-place)
        new: New usage data to add
    """
    for model_name, model_usage in new.items():
        if model_name not in total:
            # First time seeing this model, initialize with zeros
            total[model_name] = {
                "completion_tokens": 0,
                "prompt_tokens": 0,
                "total_tokens": 0,
                "completion_tokens_details": {},
                "prompt_tokens_details": {},
            }
        
        # Accumulate token counts
        for token_type in ["completion_tokens", "prompt_tokens", "total_tokens"]:
            if token_type in model_usage:
                total[model_name][token_type] += model_usage.get(token_type, 0)
        
        # For details, keep the latest non-None values
        for detail_key in ["completion_tokens_details", "prompt_tokens_details"]:
            if detail_key in model_usage and model_usage[detail_key]:
                total[model_name][detail_key] = model_usage[detail_key]
