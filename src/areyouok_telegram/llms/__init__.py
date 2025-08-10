import pydantic_ai

from areyouok_telegram.config import LOG_CHAT_MESSAGES

pydantic_ai.Agent.instrument_all(
    pydantic_ai.models.instrumented.InstrumentationSettings(include_content=LOG_CHAT_MESSAGES)
)
