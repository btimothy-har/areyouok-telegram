import pydantic_ai

from areyouok_telegram.config import LOG_CHAT_MESSAGES
from areyouok_telegram.llms.context_search import context_search_agent, search_chat_context
from areyouok_telegram.llms.utils import run_agent_with_tracking

pydantic_ai.Agent.instrument_all(
    pydantic_ai.models.instrumented.InstrumentationSettings(include_content=LOG_CHAT_MESSAGES)
)

__all__ = [
    "run_agent_with_tracking",
    "context_search_agent",
    "search_chat_context",
]
