import json
from datetime import datetime

import telegram
from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import ModelResponse
from pydantic_ai.messages import TextPart
from pydantic_ai.messages import UserPromptPart
from telegram.ext import ContextTypes


def _telegram_message_to_model_message(
    context: ContextTypes.DEFAULT_TYPE, message: telegram.Message, ts_reference: datetime
) -> ModelRequest | ModelResponse:
    """Convert a Telegram message to a model request or response."""

    msg_dict = {
        "text": message.text,
        "message_id": str(message.message_id),
        "timestamp": f"{int((ts_reference - message.date).total_seconds())} seconds ago",
    }

    if message.from_user and message.from_user.id != context.bot.id:
        return ModelRequest(
            parts=[
                UserPromptPart(
                    content=json.dumps(msg_dict),
                    timestamp=message.date,
                    part_kind="user-prompt",
                )
            ],
            kind="request",
        )
    else:
        return ModelResponse(
            parts=[TextPart(content=json.dumps(msg_dict), part_kind="text")],
            timestamp=message.date,
            kind="response",
        )


def _telegram_reaction_to_model_message(
    context: ContextTypes.DEFAULT_TYPE, reaction: telegram.MessageReactionUpdated, ts_reference: datetime
) -> ModelRequest | ModelResponse:
    """Convert a Telegram message reaction to a model request or response."""

    # TODO: Handle custom and paid reactions
    reaction_string = ", ".join([
        r.emoji for r in reaction.new_reaction if r.type == telegram.constants.ReactionType.EMOJI
    ])

    msg_dict = {
        "reaction": reaction_string,
        "to_message_id": str(reaction.message_id),
        "timestamp": f"{int((ts_reference - reaction.date).total_seconds())} seconds ago",
    }

    if reaction.user and reaction.user.id != context.bot.id:
        return ModelRequest(
            parts=[
                UserPromptPart(
                    content=json.dumps(msg_dict),
                    timestamp=reaction.date,
                    part_kind="user-prompt",
                )
            ],
            kind="request",
        )
    else:
        return ModelResponse(
            parts=[TextPart(content=json.dumps(msg_dict), part_kind="text")],
            timestamp=reaction.date,
            kind="response",
        )
