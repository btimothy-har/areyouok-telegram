"""LLM models for usage tracking and generation history."""

from areyouok_telegram.data.models.llm.llm_generation import LLMGeneration
from areyouok_telegram.data.models.llm.llm_usage import LLMUsage

__all__ = [
    "LLMGeneration",
    "LLMUsage",
]
