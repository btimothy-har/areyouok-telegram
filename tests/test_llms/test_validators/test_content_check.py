"""Tests for llms/validators/content_check.py using pydantic_ai testing."""

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from areyouok_telegram.llms.validators.content_check import ContentCheckDependencies
from areyouok_telegram.llms.validators.content_check import ContentCheckResponse
from areyouok_telegram.llms.validators.content_check import content_check_agent

# Block real model requests in tests
models.ALLOW_MODEL_REQUESTS = False
pytestmark = pytest.mark.anyio  # Mark all tests as async


class TestContentCheckAgent:
    """Test the content_check_agent using pydantic_ai test models."""

    async def test_content_check_pass(self):
        """Test content check when content passes validation."""
        # Create test model with custom response
        test_model = TestModel(
            custom_output_args={"check_pass": True, "feedback": "No Feedback Needed"}
        )

        deps = ContentCheckDependencies(check_content_exists="The message must contain a greeting")

        # Override the agent's model with test model
        with content_check_agent.override(model=test_model):
            result = await content_check_agent.run("Hello there! How are you?", deps=deps)

        assert result.output.check_pass is True
        assert result.output.feedback == "No Feedback Needed"

    async def test_content_check_fail(self):
        """Test content check when content fails validation."""
        # Create test model with failing response
        test_model = TestModel(
            custom_output_args={
                "check_pass": False,
                "feedback": "The message should include a greeting like 'hello' or 'hi'",
            }
        )

        deps = ContentCheckDependencies(check_content_exists="The message must contain a greeting")

        with content_check_agent.override(model=test_model):
            result = await content_check_agent.run("I need help with something", deps=deps)

        assert result.output.check_pass is False
        assert "greeting" in result.output.feedback.lower()

    async def test_content_check_with_complex_instruction(self):
        """Test content check with complex validation instruction."""
        test_model = TestModel(
            custom_output_args={"check_pass": True, "feedback": "No Feedback Needed"}
        )

        deps = ContentCheckDependencies(check_content_exists="The message must contain both a question and be polite")

        with content_check_agent.override(model=test_model):
            result = await content_check_agent.run("Could you please help me understand this?", deps=deps)

        assert result.output.check_pass is True

    async def test_content_check_agent_name(self):
        """Test that the agent has the correct name."""
        assert content_check_agent.name == "content_check_agent"

    async def test_content_check_output_type(self):
        """Test that the agent output type is ContentCheckResponse."""
        # The output_type should be ContentCheckResponse
        assert content_check_agent.output_type == ContentCheckResponse

    async def test_content_check_with_default_test_model(self):
        """Test content check with default TestModel behavior."""
        # Default TestModel will generate structured data based on schema
        test_model = TestModel()

        deps = ContentCheckDependencies(check_content_exists="Test instruction")

        with content_check_agent.override(model=test_model):
            result = await content_check_agent.run("Test message", deps=deps)

        # Default TestModel should generate valid output
        assert isinstance(result.output, ContentCheckResponse)
        assert isinstance(result.output.check_pass, bool)
        assert isinstance(result.output.feedback, str)

    async def test_content_check_dependencies_structure(self):
        """Test ContentCheckDependencies dataclass structure."""
        deps = ContentCheckDependencies(check_content_exists="Test requirement")

        assert deps.check_content_exists == "Test requirement"
        assert hasattr(deps, "check_content_exists")

    async def test_content_check_response_model(self):
        """Test ContentCheckResponse model structure."""
        response = ContentCheckResponse(check_pass=True, feedback="Test feedback")

        assert response.check_pass is True
        assert response.feedback == "Test feedback"

        # Test field descriptions exist
        fields = ContentCheckResponse.model_fields
        assert "check_pass" in fields
        assert "feedback" in fields
        assert fields["check_pass"].description == "Indicates whether the content check passed."
        assert "feedback" in fields["feedback"].description

    async def test_content_check_instructions_formatting(self):
        """Test that instructions are properly formatted with dependencies."""
        test_model = TestModel()

        deps = ContentCheckDependencies(check_content_exists="Must include specific keywords")

        with content_check_agent.override(model=test_model):
            result = await content_check_agent.run("This message has specific keywords", deps=deps)

            # Get the last request to verify instructions were formatted
            last_request = test_model.last_model_request_parameters

            # The agent should have received formatted instructions
            assert last_request is not None

    async def test_content_check_end_strategy(self):
        """Test that the agent uses exhaustive end strategy."""
        assert content_check_agent.end_strategy == "exhaustive"
