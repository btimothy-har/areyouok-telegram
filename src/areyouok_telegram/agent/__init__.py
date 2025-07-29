from datetime import UTC
from datetime import datetime

import telegram
from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import ModelResponse
from telegram.ext import ContextTypes

from areyouok_telegram.agent.agent import AgentDependencies
from areyouok_telegram.agent.agent import areyouok_agent
from areyouok_telegram.agent.responses import DoNothingResponse
from areyouok_telegram.agent.responses import ReactionResponse
from areyouok_telegram.agent.responses import TextResponse
from areyouok_telegram.data import MessageTypes

from .utils import _telegram_message_to_model_message
from .utils import _telegram_reaction_to_model_message

AgentResponse = TextResponse | ReactionResponse | DoNothingResponse


def convert_telegram_message_to_model_message(
    context: ContextTypes.DEFAULT_TYPE, message: MessageTypes, ts_reference: datetime | None = None
) -> ModelRequest | ModelResponse:
    """Helper function to convert a Telegram message/reaction to a model request or response."""
    ts_reference = ts_reference or datetime.now(UTC)

    if isinstance(message, telegram.MessageReactionUpdated):
        return _telegram_reaction_to_model_message(context, message, ts_reference)

    if isinstance(message, telegram.Message):
        return _telegram_message_to_model_message(context, message, ts_reference)


__all__ = [
    "areyouok_agent",
    "AgentDependencies",
    "AgentResponse",
    "convert_telegram_message_to_model_message",
]
