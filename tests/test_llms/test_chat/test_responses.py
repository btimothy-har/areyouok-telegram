"""Tests for llms/chat/responses.py."""

import pydantic
import pytest
from telegram.constants import ReactionEmoji

from areyouok_telegram.llms.chat.responses import DoNothingResponse
from areyouok_telegram.llms.chat.responses import ReactionResponse
from areyouok_telegram.llms.chat.responses import SwitchPersonalityResponse
from areyouok_telegram.llms.chat.responses import TextResponse
from areyouok_telegram.llms.chat.responses import TextWithButtonsResponse
from areyouok_telegram.llms.chat.responses import _MessageButton


class TestMessageButton:
    """Test the _MessageButton class validation."""

    def test_valid_button(self):
        """Test creating a valid message button."""
        button = _MessageButton(label="Test", callback="test_callback")
        assert button.label == "Test"
        assert button.callback == "test_callback"

    def test_label_max_length(self):
        """Test label maximum length validation."""
        # Valid length (50 chars)
        valid_label = "x" * 50
        button = _MessageButton(label=valid_label, callback="test")
        assert button.label == valid_label

        # Invalid length (51 chars)
        with pytest.raises(pydantic.ValidationError, match="String should have at most 50 characters"):
            _MessageButton(label="x" * 51, callback="test")

    def test_callback_max_length(self):
        """Test callback maximum length validation."""
        # Valid length (40 chars)
        valid_callback = "x" * 40
        button = _MessageButton(label="test", callback=valid_callback)
        assert button.callback == valid_callback

        # Invalid length (41 chars)
        with pytest.raises(pydantic.ValidationError, match="String should have at most 40 characters"):
            _MessageButton(label="test", callback="x" * 41)

    def test_label_with_emoji(self):
        """Test button label with emoji characters."""
        button = _MessageButton(label="👍 Yes", callback="yes")
        assert button.label == "👍 Yes"


class TestTextResponse:
    """Test the TextResponse class."""

    def test_valid_text_response(self):
        """Test creating a valid text response."""
        response = TextResponse(reasoning="Test reasoning", message_text="Hello world", reply_to_message_id=None)
        assert response.reasoning == "Test reasoning"
        assert response.message_text == "Hello world"
        assert response.reply_to_message_id is None
        assert response.response_type == "TextResponse"

    def test_text_response_with_reply(self):
        """Test text response with reply to message ID."""
        response = TextResponse(reasoning="Reply reasoning", message_text="This is a reply", reply_to_message_id="123")
        assert response.reply_to_message_id == "123"


class TestTextWithButtonsResponse:
    """Test the TextWithButtonsResponse class validation."""

    def test_valid_buttons_response(self):
        """Test creating a valid text with buttons response."""
        buttons = [
            _MessageButton(label="Yes", callback="yes"),
            _MessageButton(label="No", callback="no"),
        ]

        response = TextWithButtonsResponse(
            reasoning="Test reasoning",
            message_text="Do you agree?",
            reply_to_message_id=None,
            buttons=buttons,
            buttons_per_row=2,
            context="Yes/No confirmation",
        )

        assert response.message_text == "Do you agree?"
        assert len(response.buttons) == 2
        assert response.buttons_per_row == 2
        assert response.context == "Yes/No confirmation"
        assert response.response_type == "TextWithButtonsResponse"

    def test_buttons_min_length_validation(self):
        """Test minimum number of buttons validation."""
        with pytest.raises(pydantic.ValidationError, match="List should have at least 1 item"):
            TextWithButtonsResponse(
                reasoning="Test",
                message_text="Test",
                buttons=[],  # Empty list
                buttons_per_row=1,
                context="Test",
            )

    def test_buttons_max_length_validation(self):
        """Test maximum number of buttons validation."""
        buttons = [
            _MessageButton(label=f"Option {i}", callback=f"opt{i}")
            for i in range(4)  # 4 buttons (max is 3)
        ]

        with pytest.raises(pydantic.ValidationError, match="List should have at most 3 items"):
            TextWithButtonsResponse(
                reasoning="Test", message_text="Test", buttons=buttons, buttons_per_row=2, context="Test"
            )

    def test_buttons_per_row_min_validation(self):
        """Test buttons_per_row minimum value validation."""
        buttons = [_MessageButton(label="Test", callback="test")]

        with pytest.raises(pydantic.ValidationError, match="Input should be greater than or equal to 1"):
            TextWithButtonsResponse(
                reasoning="Test",
                message_text="Test",
                buttons=buttons,
                buttons_per_row=0,  # Invalid: less than 1
                context="Test",
            )

    def test_buttons_per_row_max_validation(self):
        """Test buttons_per_row maximum value validation."""
        buttons = [_MessageButton(label="Test", callback="test")]

        with pytest.raises(pydantic.ValidationError, match="Input should be less than or equal to 5"):
            TextWithButtonsResponse(
                reasoning="Test",
                message_text="Test",
                buttons=buttons,
                buttons_per_row=6,  # Invalid: greater than 5
                context="Test",
            )

    def test_maximum_valid_configuration(self):
        """Test maximum valid button configuration (3 buttons, 5 per row)."""
        buttons = [
            _MessageButton(label="Option 1", callback="opt1"),
            _MessageButton(label="Option 2", callback="opt2"),
            _MessageButton(label="Option 3", callback="opt3"),
        ]

        response = TextWithButtonsResponse(
            reasoning="Test reasoning",
            message_text="Choose an option:",
            buttons=buttons,
            buttons_per_row=5,  # All buttons in one row
            context="Multiple choice selection",
        )

        assert len(response.buttons) == 3
        assert response.buttons_per_row == 5


class TestReactionResponse:
    """Test the ReactionResponse class."""

    def test_valid_reaction_response(self):
        """Test creating a valid reaction response."""
        response = ReactionResponse(
            reasoning="User said something funny", react_to_message_id="123", emoji=ReactionEmoji.THUMBS_UP
        )

        assert response.reasoning == "User said something funny"
        assert response.react_to_message_id == "123"
        assert response.emoji == ReactionEmoji.THUMBS_UP
        assert response.response_type == "ReactionResponse"


class TestSwitchPersonalityResponse:
    """Test the SwitchPersonalityResponse class."""

    def test_valid_personality_switch(self):
        """Test switching to a valid personality."""
        response = SwitchPersonalityResponse(reasoning="User needs celebration", personality="celebration")

        assert response.reasoning == "User needs celebration"
        assert response.personality == "celebration"
        assert response.response_type == "SwitchPersonalityResponse"

    def test_invalid_personality(self):
        """Test validation of personality values."""
        with pytest.raises(pydantic.ValidationError, match="Input should be"):
            SwitchPersonalityResponse(reasoning="Test", personality="invalid_personality")

    def test_all_valid_personalities(self):
        """Test all valid personality options."""
        valid_personalities = ["anchoring", "celebration", "exploration", "witnessing"]

        for personality in valid_personalities:
            response = SwitchPersonalityResponse(reasoning=f"Switch to {personality}", personality=personality)
            assert response.personality == personality


class TestDoNothingResponse:
    """Test the DoNothingResponse class."""

    def test_do_nothing_response(self):
        """Test creating a do nothing response."""
        response = DoNothingResponse(reasoning="No action needed right now")

        assert response.reasoning == "No action needed right now"
        assert response.response_type == "DoNothingResponse"


class TestBaseAgentResponse:
    """Test base response functionality."""

    def test_response_type_property(self):
        """Test that response_type returns the correct class name."""
        text_response = TextResponse(reasoning="test", message_text="test")
        assert text_response.response_type == "TextResponse"

        reaction_response = ReactionResponse(reasoning="test", react_to_message_id="123", emoji=ReactionEmoji.THUMBS_UP)
        assert reaction_response.response_type == "ReactionResponse"

        buttons_response = TextWithButtonsResponse(
            reasoning="test",
            message_text="test",
            buttons=[_MessageButton(label="Test", callback="test")],
            buttons_per_row=1,
            context="test",
        )
        assert buttons_response.response_type == "TextWithButtonsResponse"
