# ruff: noqa: TRY003

import telegram
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider

from areyouok_telegram.config import ENV
from areyouok_telegram.config import OPENROUTER_API_KEY
from areyouok_telegram.data import MessageTypes

pydantic_ai_instrumentation = InstrumentationSettings(include_content=True if ENV == "development" else False)

openrouter_provider = OpenRouterProvider(api_key=OPENROUTER_API_KEY)


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
            "text": message.text or message.caption or "",
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
