import dspy

from areyouok_telegram.config import OPENROUTER_API_KEY
from areyouok_telegram.llms.analytics.context import DynamicContextCompression

dspy.settings.configure(
    lm=dspy.LM(
        "openai/openai/gpt-4.1-nano",
        temperature=0,
        api_key=OPENROUTER_API_KEY,
        api_base="https://openrouter.ai/api/v1",
        cache=False,
        max_tokens=128_000,
    ),
    track_usage=True,
)

__all__ = [
    "DynamicContextCompression",
]
