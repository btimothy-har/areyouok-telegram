import logging
from dataclasses import dataclass

from pydantic_ai import Agent
from telegram.ext import ContextTypes

from areyouok_telegram.data.connection import AsyncSessionLocal

logger = logging.getLogger(__name__)


@dataclass
class AgentDependencies:
    """Context data passed to the LLM agent for making decisions."""

    tg_context: ContextTypes.DEFAULT_TYPE
    tg_chat_id: str
    db_connection: AsyncSessionLocal
    error: Exception | None = None


areyouok_agent = Agent(
    model="openai:gpt-4o",
    instructions="Do not reply to all of a user's messages. Pick the most relevant one to reply to.",
    deps_type=AgentDependencies,
    name="areyouok_telegram_agent",
    end_strategy="exhaustive",
)
