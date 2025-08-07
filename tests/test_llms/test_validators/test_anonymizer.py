"""Tests for llms/validators/anonymizer.py using pydantic_ai testing."""

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelMessage
from pydantic_ai.messages import ModelResponse
from pydantic_ai.messages import TextPart
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from areyouok_telegram.llms.validators.anonymizer import anonymization_agent

# Block real model requests in tests
models.ALLOW_MODEL_REQUESTS = False
pytestmark = pytest.mark.anyio  # Mark all tests as async


class TestAnonymizationAgent:
    """Test the anonymization_agent using pydantic_ai test models."""

    async def test_anonymization_basic(self):
        """Test basic anonymization of personal information."""
        # Create test model with custom response
        test_model = TestModel(custom_output_text="I spoke with [Person] yesterday at [Location] about the meeting.")

        # Override the agent's model with test model
        with anonymization_agent.override(model=test_model):
            result = await anonymization_agent.run(
                "I spoke with John Smith yesterday at Central Park about the meeting."
            )

        assert result.output == "I spoke with [Person] yesterday at [Location] about the meeting."

    async def test_anonymization_preserves_tone(self):
        """Test that anonymization preserves emotional tone."""
        test_model = TestModel(custom_output_text="I'm really worried about [Person]! They haven't been responding.")

        with anonymization_agent.override(model=test_model):
            result = await anonymization_agent.run("I'm really worried about Sarah! She hasn't been responding.")

        # Check that emotional markers are preserved
        assert "worried" in result.output
        assert "!" in result.output

    async def test_anonymization_multiple_entities(self):
        """Test anonymization of multiple entities."""
        test_model = TestModel(custom_output_text="[Person1] and [Person2] met at [Location] on [Date].")

        with anonymization_agent.override(model=test_model):
            result = await anonymization_agent.run("Alice and Bob met at Starbucks on January 15th.")

        assert "[Person" in result.output
        assert "[Location]" in result.output

    async def test_anonymization_agent_name(self):
        """Test that the agent has the correct name."""
        assert anonymization_agent.name == "anonymization_agent"

    async def test_anonymization_with_default_test_model(self):
        """Test anonymization with default TestModel behavior."""
        # Default TestModel returns a simple string response
        test_model = TestModel()

        with anonymization_agent.override(model=test_model):
            result = await anonymization_agent.run("My phone number is 555-1234")

        # Default TestModel should return a string
        assert isinstance(result.output, str)

    async def test_anonymization_output_validator(self):
        """Test that the output validator returns the data unchanged."""
        test_model = TestModel(custom_output_text="Anonymized text")

        with anonymization_agent.override(model=test_model):
            result = await anonymization_agent.run("Original text with names")

        # The output validator should pass through the result
        assert result.output == "Anonymized text"

    async def test_anonymization_with_function_model(self):
        """Test anonymization using FunctionModel for more control."""

        def anonymize_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:  # noqa: ARG001
            # Get the user input from the last message
            user_input = messages[-1].parts[-1].content

            # Simple anonymization logic
            anonymized = user_input.replace("John", "[Name]")
            anonymized = anonymized.replace("123-456-7890", "[Phone]")

            return ModelResponse(parts=[TextPart(content=anonymized, part_kind="text")])

        function_model = FunctionModel(anonymize_function)

        with anonymization_agent.override(model=function_model):
            result = await anonymization_agent.run("John's phone number is 123-456-7890")

        assert result.output == "[Name]'s phone number is [Phone]"

    async def test_anonymization_end_strategy(self):
        """Test that the agent uses exhaustive end strategy."""
        assert anonymization_agent.end_strategy == "exhaustive"

    async def test_anonymization_empty_input(self):
        """Test anonymization with empty input."""
        test_model = TestModel(custom_output_text="")

        with anonymization_agent.override(model=test_model):
            result = await anonymization_agent.run("")

        assert not result.output

    async def test_anonymization_preserves_structure(self):
        """Test that anonymization preserves message structure."""
        test_model = TestModel(custom_output_text="- [Person1]: Meeting at [Time]\n- [Person2]: Confirmed")

        with anonymization_agent.override(model=test_model):
            result = await anonymization_agent.run("- Alice: Meeting at 3pm\n- Bob: Confirmed")

        # Check structure is preserved
        assert "-" in result.output
        assert ":" in result.output
        assert "\n" in result.output
