"""Tests for chat constants."""

from datetime import datetime
from zoneinfo import ZoneInfo

from areyouok_telegram.llms.chat.constants import USER_PREFERENCES


class TestUserPreferencesConstant:
    """Test USER_PREFERENCES constant usage."""

    def test_user_preferences_template_formatting(self):
        """Test USER_PREFERENCES template can be formatted correctly."""
        formatted = USER_PREFERENCES.format(
            preferred_name="Alice",
            country="USA",
            timezone="America/New_York",
            current_time=datetime(2025, 1, 1, 15, 30, 0, tzinfo=ZoneInfo("America/New_York")),
            communication_style="casual and friendly",
        )

        assert "Preferred Name: Alice" in formatted
        assert "Country: USA" in formatted
        assert "Timezone: America/New_York" in formatted
        assert "Current Time:" in formatted
        assert "2025-01-01 15:30:00-05:00" in formatted
        assert "Communication Style: casual and friendly" in formatted

    def test_user_preferences_template_with_none_current_time(self):
        """Test USER_PREFERENCES template with None current_time."""
        formatted = USER_PREFERENCES.format(
            preferred_name="Bob",
            country="CAN",
            timezone="rather_not_say",
            current_time=None,
            communication_style="professional",
        )

        assert "Preferred Name: Bob" in formatted
        assert "Country: CAN" in formatted
        assert "Timezone: rather_not_say" in formatted
        assert "Current Time: None" in formatted
        assert "Communication Style: professional" in formatted

    def test_user_preferences_mentions_settings_command(self):
        """Test USER_PREFERENCES template mentions /settings command."""
        formatted = USER_PREFERENCES.format(
            preferred_name="Test", country="Test", timezone="UTC", current_time=None, communication_style="Test"
        )

        assert "/settings" in formatted
        assert "update their preferred name, country, and timezone" in formatted
