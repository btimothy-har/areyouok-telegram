"""Tests for the content check agent functionality using PydanticAI TestModel.

Testing Strategy:
1. Agent run tests: Focus on testing that the agent produces valid ContentCheckResponse
2. Instructions tests: Test that the instruction function generates correct instructions
3. Different scenarios: Test various content validation scenarios
"""

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import Usage

from areyouok_telegram.llms.analytics import ContentCheckDependencies
from areyouok_telegram.llms.analytics import ContentCheckResponse
from areyouok_telegram.llms.analytics import content_check_agent
from areyouok_telegram.llms.analytics.content_check import content_check_instructions


@pytest.fixture
def override_content_check_agent():
    with content_check_agent.override(model=TestModel()):
        yield


@pytest.mark.usefixtures("override_content_check_agent")
class TestContentCheckAgent:
    """Test suite for the content check agent functionality."""

    @pytest.mark.asyncio
    async def test_agent_basic_response(self):
        """Test basic agent response generation using TestModel."""
        # Create mock dependencies
        test_deps = ContentCheckDependencies(
            check_content_exists="The user sent a video file, but you can only view images and PDFs."
        )

        result = await content_check_agent.run(
            user_prompt="I noticed you sent a video. Unfortunately, I can only process images and PDFs.",
            deps=test_deps,
        )

        # TestModel returns a summary by default, but should be parsed as ContentCheckResponse
        assert result.output is not None
        assert isinstance(result.output, ContentCheckResponse)
        assert isinstance(result.output.check_pass, bool)
        assert isinstance(result.output.feedback, str)

    @pytest.mark.asyncio
    async def test_agent_content_adheres(self):
        """Test agent when content adheres to instruction."""
        # Create mock dependencies
        test_deps = ContentCheckDependencies(
            check_content_exists="The user sent a video file, but you can only view images and PDFs."
        )

        result = await content_check_agent.run(
            user_prompt=(
                "I see you've uploaded a video file. I can only view images and PDFs, so I won't be able "
                "to see the video content."
            ),
            deps=test_deps,
        )

        # Should recognize that the content adheres
        assert isinstance(result.output, ContentCheckResponse)
        # Note: With TestModel, we can't control the exact output, but we can verify structure

    @pytest.mark.asyncio
    async def test_agent_content_not_adheres(self):
        """Test agent when content doesn't adhere to instruction."""
        # Create mock dependencies
        test_deps = ContentCheckDependencies(
            check_content_exists="The user sent a video file, but you can only view images and PDFs."
        )

        result = await content_check_agent.run(
            user_prompt="How are you feeling today? Tell me about your day.",
            deps=test_deps,
        )

        # Should recognize that the content doesn't adhere
        assert isinstance(result.output, ContentCheckResponse)
        assert isinstance(result.output.check_pass, bool)
        assert isinstance(result.output.feedback, str)

    @pytest.mark.asyncio
    async def test_agent_implicit_adherence(self):
        """Test agent recognizes implicit adherence to instruction."""
        # Create mock dependencies
        test_deps = ContentCheckDependencies(
            check_content_exists="The user sent a video file, but you can only view images and PDFs."
        )

        result = await content_check_agent.run(
            user_prompt=(
                "Thanks for sharing that video. Could you describe what's in it since I can't view video files?"
            ),
            deps=test_deps,
        )

        # Should recognize implicit adherence
        assert isinstance(result.output, ContentCheckResponse)

    @pytest.mark.asyncio
    async def test_agent_with_different_instructions(self):
        """Test agent with various instruction types."""
        instructions = [
            "The user sent an audio file, but you can only view images and PDFs.",
            "The user sent multiple files including unsupported formats.",
            "Please acknowledge that you received the files.",
        ]

        for instruction in instructions:
            test_deps = ContentCheckDependencies(check_content_exists=instruction)

            result = await content_check_agent.run(
                user_prompt="I understand you've sent some files. Let me see what I can help with.",
                deps=test_deps,
            )

            assert isinstance(result.output, ContentCheckResponse)
            assert hasattr(result.output, "check_pass")
            assert hasattr(result.output, "feedback")


class TestContentCheckInstructions:
    """Test suite for the content check instructions function."""

    def test_instructions_generation(self):
        """Test that instructions are generated correctly."""
        # Create mock context
        test_deps = ContentCheckDependencies(check_content_exists="Test instruction content")

        ctx = RunContext(
            deps=test_deps,
            messages=[],
            retry=0,
            model=TestModel(),
            usage=Usage(),
        )

        # Generate instructions
        instructions = content_check_instructions(ctx)

        # Verify instructions contain the required content
        assert isinstance(instructions, str)
        assert "Test instruction content" in instructions
        assert "validate" in instructions.lower()
        assert "message adheres" in instructions.lower()
        assert "feedback" in instructions.lower()

    def test_instructions_with_complex_content(self):
        """Test instructions with complex check content."""
        # Create mock context with complex instruction
        test_deps = ContentCheckDependencies(
            check_content_exists=(
                "The user sent video/mp4, audio/mpeg, and application/msword files, "
                "but you can only view images and PDFs."
            )
        )

        ctx = RunContext(
            deps=test_deps,
            messages=[],
            retry=0,
            model=TestModel(),
            usage=Usage(),
        )

        # Generate instructions
        instructions = content_check_instructions(ctx)

        # Verify instructions contain all the mime types
        assert "video/mp4" in instructions
        assert "audio/mpeg" in instructions
        assert "application/msword" in instructions
        assert "images and PDFs" in instructions

    def test_instructions_formatting(self):
        """Test that instructions are properly formatted."""
        # Create mock context
        test_deps = ContentCheckDependencies(check_content_exists="Simple check")

        ctx = RunContext(
            deps=test_deps,
            messages=[],
            retry=0,
            model=TestModel(),
            usage=Usage(),
        )

        # Generate instructions
        instructions = content_check_instructions(ctx)

        # Verify content
        assert '"Simple check"' in instructions  # Check content is quoted
        assert "No Feedback Needed" in instructions  # Contains the success feedback
        assert "validate" in instructions.lower()  # Contains validation instruction


@pytest.mark.usefixtures("override_content_check_agent")
class TestContentCheckIntegration:
    """Integration tests for content check agent."""

    @pytest.mark.asyncio
    async def test_agent_model_configuration(self):
        """Test that the agent is properly configured."""
        # Verify agent properties
        assert content_check_agent.name == "content_check_agent"
        # The agent is configured with ContentCheckResponse as output type
        # We can verify this by running the agent and checking the output type

    @pytest.mark.asyncio
    async def test_agent_with_empty_prompt(self):
        """Test agent behavior with empty user prompt."""
        test_deps = ContentCheckDependencies(check_content_exists="The user sent a file.")

        result = await content_check_agent.run(
            user_prompt="",
            deps=test_deps,
        )

        # Should still return valid response
        assert isinstance(result.output, ContentCheckResponse)
        assert result.output.check_pass is not None
        assert result.output.feedback is not None

    @pytest.mark.asyncio
    async def test_response_model_fields(self):
        """Test ContentCheckResponse model fields."""
        # Create a response instance
        response = ContentCheckResponse(check_pass=True, feedback="No Feedback Needed")

        # Verify fields
        assert response.check_pass is True
        assert response.feedback == "No Feedback Needed"

        # Test with failure case
        response_fail = ContentCheckResponse(check_pass=False, feedback="You should acknowledge the uploaded files.")

        assert response_fail.check_pass is False
        assert "acknowledge" in response_fail.feedback
