"""Tests for llms/agent_journal_setup.py using pydantic_ai testing."""

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.exceptions import ModelRetry

from areyouok_telegram.llms.agent_journal_setup import (
    JournalPrompts,
    generate_instructions,
    journal_prompts_agent,
    validate_prompts_output,
)

# Block real model requests in tests
models.ALLOW_MODEL_REQUESTS = False
pytestmark = pytest.mark.anyio  # Mark all tests as async


class TestJournalPromptsModel:
    """Test JournalPrompts model."""

    def test_journal_prompts_creation(self):
        """Test JournalPrompts can be created with 3 prompts."""
        prompts = JournalPrompts(
            prompts=[
                "What brought you joy today?",
                "What challenge did you face?",
                "What are you grateful for?",
            ]
        )

        assert len(prompts.prompts) == 3
        assert prompts.prompts[0] == "What brought you joy today?"

    def test_journal_prompts_validation_min_length(self):
        """Test JournalPrompts validates minimum length."""
        with pytest.raises(ValueError):
            JournalPrompts(prompts=["Only one prompt"])

    def test_journal_prompts_validation_max_length(self):
        """Test JournalPrompts validates maximum length."""
        with pytest.raises(ValueError):
            JournalPrompts(prompts=["Prompt 1", "Prompt 2", "Prompt 3", "Prompt 4"])


class TestJournalPromptsAgentValidation:
    """Test journal prompts agent output validation."""

    @pytest.mark.asyncio
    async def test_validate_prompts_output_success(self):
        """Test successful validation of 3 unique prompts."""
        prompts = JournalPrompts(
            prompts=[
                "What brought you joy today?",
                "What challenge did you face?",
                "What are you grateful for?",
            ]
        )

        result = await validate_prompts_output(ctx=None, data=prompts)

        assert result == prompts

    @pytest.mark.asyncio
    async def test_validate_prompts_output_duplicate(self):
        """Test validation fails with duplicate prompts."""
        prompts = JournalPrompts(
            prompts=[
                "What brought you joy today?",
                "What brought you joy today?",
                "What are you grateful for?",
            ]
        )

        with pytest.raises(ModelRetry, match="Prompts must be unique"):
            await validate_prompts_output(ctx=None, data=prompts)

    @pytest.mark.asyncio
    async def test_validate_prompts_output_empty_prompt(self):
        """Test validation fails with empty prompt."""
        prompts = JournalPrompts(prompts=["What brought you joy today?", "", "What are you grateful for?"])

        with pytest.raises(ModelRetry, match="Prompts cannot be empty"):
            await validate_prompts_output(ctx=None, data=prompts)


class TestJournalPromptsAgent:
    """Test journal prompts agent."""

    def test_journal_prompts_agent_configuration(self):
        """Test agent is configured correctly."""
        assert journal_prompts_agent.name == "journal_prompts_agent"
        assert journal_prompts_agent.output_type == JournalPrompts

    @pytest.mark.asyncio
    async def test_agent_generates_instructions(self):
        """Test agent generates appropriate instructions."""
        mock_ctx = MagicMock()

        result = generate_instructions(mock_ctx)

        # Check that instructions contain expected elements
        assert "journaling" in result.lower()
        assert "prompts" in result.lower()
        assert "gratitude and appreciation" in result.lower()
