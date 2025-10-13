"""Tests for llms/profile_generation/agent.py using pydantic_ai testing."""

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from areyouok_telegram.llms.profile_generation import ProfileTemplate
from areyouok_telegram.llms.profile_generation import profile_generation_agent

# Block real model requests in tests
models.ALLOW_MODEL_REQUESTS = False
pytestmark = pytest.mark.anyio  # Mark all tests as async


class TestProfileGenerationAgent:
    """Test the profile_generation_agent using pydantic_ai test models."""

    async def test_agent_has_correct_name(self):
        """Test that the agent has the correct name."""
        assert profile_generation_agent.name == "profile_generation_agent"

    async def test_agent_output_type(self):
        """Test that the agent output type is ProfileTemplate."""
        assert profile_generation_agent.output_type == ProfileTemplate

    async def test_profile_generation_with_test_model(self):
        """Test profile generation with TestModel produces valid structure."""
        test_model = TestModel()

        with profile_generation_agent.override(model=test_model):
            result = await profile_generation_agent.run("Generate a profile from these contexts.")

        # Verify output is correct type
        assert isinstance(result.output, ProfileTemplate)

        # Verify all required fields exist
        assert hasattr(result.output, "identity_markers")
        assert hasattr(result.output, "strengths_values")
        assert hasattr(result.output, "goals_outcomes")
        assert hasattr(result.output, "emotional_patterns")
        assert hasattr(result.output, "safety_plan")
        assert hasattr(result.output, "change_log")

        # Verify fields are strings
        assert isinstance(result.output.identity_markers, str)
        assert isinstance(result.output.strengths_values, str)
        assert isinstance(result.output.goals_outcomes, str)
        assert isinstance(result.output.emotional_patterns, str)
        assert isinstance(result.output.safety_plan, str)
        assert isinstance(result.output.change_log, str)

    async def test_profile_generation_with_custom_output(self):
        """Test profile generation with custom TestModel output."""
        custom_output = {
            "identity_markers": "Professional software engineer, prefers they/them pronouns",
            "strengths_values": "Strong problem-solving skills (Empowerment), values meaningful work (Meaning)",
            "goals_outcomes": "Short-term: Complete current project. Long-term: Lead a team",
            "emotional_patterns": "Tends to feel anxious before deadlines but manages well with planning",
            "safety_plan": "Warning signs: Increased irritability, trouble sleeping",
            "change_log": "Initial profile generation based on first 3 conversations",
        }

        test_model = TestModel(custom_output_args=custom_output)

        with profile_generation_agent.override(model=test_model):
            result = await profile_generation_agent.run("Generate profile")

        assert result.output.identity_markers == custom_output["identity_markers"]
        assert result.output.strengths_values == custom_output["strengths_values"]
        assert result.output.goals_outcomes == custom_output["goals_outcomes"]
        assert result.output.emotional_patterns == custom_output["emotional_patterns"]
        assert result.output.safety_plan == custom_output["safety_plan"]
        assert result.output.change_log == custom_output["change_log"]

    async def test_profile_template_content_property(self):
        """Test ProfileTemplate.content property formats correctly."""
        profile = ProfileTemplate(
            identity_markers="Test identity",
            strengths_values="Test strengths",
            goals_outcomes="Test goals",
            emotional_patterns="Test patterns",
            safety_plan="Test safety plan",
            change_log="Test changelog",
        )

        content = profile.content

        # Verify content includes all sections
        assert "# User Profile" in content
        assert "## Identity Markers" in content
        assert "## Strengths & Values (CHIME Framework)" in content
        assert "## Goals & Outcomes" in content
        assert "## Emotional Patterns" in content
        assert "## Safety Plan" in content

        # Verify actual content is included
        assert "Test identity" in content
        assert "Test strengths" in content
        assert "Test goals" in content
        assert "Test patterns" in content
        assert "Test safety plan" in content

        # Verify change_log is NOT in content (it's separate)
        assert "Test changelog" not in content
        assert "change_log" not in content.lower()

    async def test_profile_template_model_fields(self):
        """Test ProfileTemplate model has correct field descriptions."""
        # Access field info
        fields = ProfileTemplate.model_fields

        assert "identity_markers" in fields
        assert "strengths_values" in fields
        assert "goals_outcomes" in fields
        assert "emotional_patterns" in fields
        assert "safety_plan" in fields
        assert "change_log" in fields

        # Verify all fields have descriptions
        for field_info in fields.values():
            assert field_info.description is not None
            assert len(field_info.description) > 0
