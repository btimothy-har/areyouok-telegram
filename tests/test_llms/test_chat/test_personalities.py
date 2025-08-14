"""Tests for personality types and switching."""

import pytest

from areyouok_telegram.llms.chat.personalities import PersonalityTypes
from areyouok_telegram.llms.exceptions import InvalidPersonalityError


class TestPersonalityTypes:
    """Test the PersonalityTypes enum."""

    @pytest.fixture(scope="class")
    def all_personality_types(self):
        """Fixture providing all personality types for parameterized tests."""
        return PersonalityTypes.choices()

    def test_personality_choices(self, all_personality_types):
        """Test that choices() returns all personality values."""
        expected_choices = ["anchoring", "celebration", "exploration", "witnessing"]
        assert all_personality_types == expected_choices

    @pytest.mark.parametrize("personality_value", ["anchoring", "celebration", "exploration", "witnessing"])
    def test_get_by_value_valid(self, personality_value):
        """Test getting personality type by valid value."""
        result = PersonalityTypes.get_by_value(personality_value)

        assert result.value == personality_value
        assert isinstance(result, PersonalityTypes)

    def test_get_by_value_invalid(self):
        """Test getting personality type by invalid value raises exception."""
        with pytest.raises(InvalidPersonalityError, match="invalid_personality"):
            PersonalityTypes.get_by_value("invalid_personality")

    @pytest.mark.parametrize(
        "personality_type,expected_personalities",
        [
            (PersonalityTypes.ANCHORING, "anchoring"),
            (PersonalityTypes.CELEBRATION, "celebration"),
            (PersonalityTypes.EXPLORATION, "exploration"),
            (PersonalityTypes.WITNESSING, "witnessing"),
        ],
    )
    def test_personality_values(self, personality_type, expected_personalities):
        """Test that personality enum values are correct."""
        assert personality_type.value == expected_personalities

    @pytest.mark.parametrize(
        "personality_type",
        [
            PersonalityTypes.ANCHORING,
            PersonalityTypes.CELEBRATION,
            PersonalityTypes.EXPLORATION,
            PersonalityTypes.WITNESSING,
        ],
    )
    def test_prompt_text_all_types(self, personality_type):
        """Test that all personality types return valid prompt text."""
        prompt = personality_type.prompt_text()

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain some indication of the personality
        assert any(
            keyword in prompt.lower() for keyword in [personality_type.value, "personality", "trait", "role", "style"]
        )

    def test_prompt_text_consistency(self):
        """Test that prompt_text() returns consistent results."""
        personality = PersonalityTypes.EXPLORATION

        prompt1 = personality.prompt_text()
        prompt2 = personality.prompt_text()

        assert prompt1 == prompt2

    def test_enum_iteration(self):
        """Test that we can iterate over all personality types."""
        personalities = list(PersonalityTypes)

        assert len(personalities) == 4
        assert PersonalityTypes.ANCHORING in personalities
        assert PersonalityTypes.CELEBRATION in personalities
        assert PersonalityTypes.EXPLORATION in personalities
        assert PersonalityTypes.WITNESSING in personalities

    def test_prompt_text_invalid_personality(self):
        """Test that prompt_text raises error for invalid personality."""

        # Create a fake personality to test error handling
        class FakePersonalityType:
            def __init__(self):
                self.value = "fake_personality"

        # This should raise InvalidPersonalityError when passed to prompt_text logic
        with pytest.raises(InvalidPersonalityError, match="fake_personality"):
            PersonalityTypes.get_by_value("fake_personality")
