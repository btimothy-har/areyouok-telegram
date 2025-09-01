"""Tests for chat prompt template."""

from areyouok_telegram.llms.chat.prompt import BaseChatPromptTemplate


class TestBaseChatPromptTemplate:
    """Test BaseChatPromptTemplate functionality."""

    def test_prompt_template_creation_with_defaults(self):
        """Test BaseChatPromptTemplate creation with default values."""
        template = BaseChatPromptTemplate(response="Test response")

        assert template.response == "Test response"
        assert template.message is None
        assert template.objectives is None
        assert template.personality is None
        assert template.user_preferences is None
        # Default values should be set from constants
        assert template.identity
        assert template.rules
        assert template.knowledge

    def test_prompt_template_creation_with_user_preferences(self):
        """Test BaseChatPromptTemplate creation with user preferences."""
        user_prefs = "Preferred Name: Alice\nCountry: USA"

        template = BaseChatPromptTemplate(response="Test response", user_preferences=user_prefs)

        assert template.user_preferences == user_prefs

    def test_as_prompt_string_with_user_preferences(self):
        """Test as_prompt_string includes user preferences section."""
        user_prefs = "Preferred Name: Bob\nTimezone: UTC"

        template = BaseChatPromptTemplate(response="Test response", user_preferences=user_prefs)

        result = template.as_prompt_string()

        assert "<user_preferences>" in result
        assert user_prefs in result
        assert "</user_preferences>" in result

    def test_as_prompt_string_without_user_preferences(self):
        """Test as_prompt_string excludes user preferences when None."""
        template = BaseChatPromptTemplate(response="Test response")

        result = template.as_prompt_string()

        assert "<user_preferences>" not in result
        assert "</user_preferences>" not in result

    def test_as_prompt_string_structure_with_all_fields(self):
        """Test as_prompt_string includes all sections when provided."""
        template = BaseChatPromptTemplate(
            response="Test response",
            message="Important message",
            objectives="Test objectives",
            personality="Test personality",
            user_preferences="Test preferences",
        )

        result = template.as_prompt_string()

        # Verify all sections are present
        assert "<identity>" in result and "</identity>" in result
        assert "<rules>" in result and "</rules>" in result
        assert "<response>" in result and "</response>" in result
        assert "<knowledge>" in result and "</knowledge>" in result
        assert "<message>" in result and "</message>" in result
        assert "<objectives>" in result and "</objectives>" in result
        assert "<personality>" in result and "</personality>" in result
        assert "<user_preferences>" in result and "</user_preferences>" in result
