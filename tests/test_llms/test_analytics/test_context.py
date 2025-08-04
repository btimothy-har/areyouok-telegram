"""Tests for the context compression agent using PydanticAI TestModel."""

import pytest
from pydantic_ai.models.test import TestModel

from areyouok_telegram.llms.analytics.context import ContextTemplate
from areyouok_telegram.llms.analytics.context import context_compression_agent


@pytest.fixture
def override_context_agent():
    """Override the context compression agent with TestModel."""
    with context_compression_agent.override(model=TestModel()):
        yield


@pytest.mark.usefixtures("override_context_agent")
class TestContextCompressionAgent:
    """Test the context compression agent functionality."""

    @pytest.mark.asyncio
    async def test_agent_produces_context_template(self):
        """Test agent produces valid ContextTemplate output."""
        result = await context_compression_agent.run("Test user prompt")

        # Verify the response is ContextTemplate with required fields
        assert isinstance(result.output, ContextTemplate)
        assert hasattr(result.output, "life_situation")
        assert hasattr(result.output, "connection")
        assert hasattr(result.output, "personal_context")
        assert hasattr(result.output, "conversation")
        assert hasattr(result.output, "practical_matters")
        assert hasattr(result.output, "feedback")
        assert hasattr(result.output, "others")

    @pytest.mark.asyncio
    async def test_agent_with_empty_messages(self):
        """Test agent handles empty message history."""
        result = await context_compression_agent.run()

        # Should still produce valid ContextTemplate
        assert isinstance(result.output, ContextTemplate)
        # TestModel should produce some default content
        assert result.output.content is not None
        assert isinstance(result.output.content, str)

    @pytest.mark.asyncio
    async def test_agent_formats_content_correctly(self):
        """Test agent formats the content with proper sections."""
        result = await context_compression_agent.run(user_prompt="Test user prompt")

        # Verify content is formatted with sections
        content = result.output.content
        assert "## Life Situation" in content
        assert "## Connection" in content
        assert "## Personal Context" in content
        assert "## Conversation" in content
        assert "## Practical Matters" in content
        assert "## Feedback" in content
        assert "## Others" in content

    @pytest.mark.asyncio
    async def test_agent_usage_tracking(self):
        """Test agent tracks usage properly."""
        result = await context_compression_agent.run(user_prompt="Test user prompt")

        # Verify usage data is available
        usage = result.usage()
        assert usage is not None
        assert hasattr(usage, "request_tokens")
        assert hasattr(usage, "response_tokens")
        assert hasattr(usage, "total_tokens")
