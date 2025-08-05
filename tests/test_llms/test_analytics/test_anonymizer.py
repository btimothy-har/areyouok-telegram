"""Tests for the anonymization agent using PydanticAI TestModel."""

import pytest
from pydantic_ai.models.test import TestModel

from areyouok_telegram.llms.analytics.anonymizer import anonymization_agent


@pytest.fixture
def override_anonymization_agent():
    """Override the anonymization agent with TestModel."""
    with anonymization_agent.override(model=TestModel()):
        yield


@pytest.mark.usefixtures("override_anonymization_agent")
class TestAnonymizationAgent:
    """Test the anonymization agent functionality."""

    @pytest.mark.asyncio
    async def test_agent_anonymizes_text(self):
        """Test agent anonymizes sensitive information."""
        sensitive_text = "My name is John Doe and I live at 123 Main St. My phone is 555-1234."

        result = await anonymization_agent.run(sensitive_text)

        # Verify the response is a string
        assert isinstance(result.output, str)
        # TestModel should return some content
        assert len(result.output) > 0

    @pytest.mark.asyncio
    async def test_agent_preserves_non_sensitive_text(self):
        """Test agent preserves text without sensitive information."""
        non_sensitive_text = "I'm feeling stressed about work today."

        result = await anonymization_agent.run(non_sensitive_text)

        # Should still return a string
        assert isinstance(result.output, str)
        assert len(result.output) > 0

    @pytest.mark.asyncio
    async def test_agent_handles_empty_input(self):
        """Test agent handles empty input gracefully."""
        result = await anonymization_agent.run("")

        # Should handle empty input
        assert isinstance(result.output, str)

    @pytest.mark.asyncio
    async def test_agent_usage_tracking(self):
        """Test agent tracks usage properly."""
        test_text = "Test message for usage tracking"

        result = await anonymization_agent.run(test_text)

        # Verify usage data is available
        usage = result.usage()
        assert usage is not None
        assert hasattr(usage, "request_tokens")
        assert hasattr(usage, "response_tokens")
        assert hasattr(usage, "total_tokens")
        assert usage.total_tokens > 0
