"""Tests for ChatEvent model."""

import json
import os
import sys
from unittest.mock import MagicMock

import pydantic_ai
import pytest
import telegram

from areyouok_telegram.data.models.chat_event import SYSTEM_USER_ID
from areyouok_telegram.data.models.chat_event import ChatEvent
from areyouok_telegram.data.models.context import ContextType
from areyouok_telegram.data.models.media import MediaFiles

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))
from helpers.chat_helpers import assert_json_content_structure
from helpers.chat_helpers import assert_model_message_format


class TestChatEvent:
    """Test the ChatEvent model."""

    def test_from_message_text(self, mock_messages_sqlalchemy, mock_telegram_message):
        """Test creating ChatEvent from text message."""
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        result = ChatEvent.from_message(mock_messages_sqlalchemy, [])

        assert result.event_type == "message"
        assert result.event_data["text"] == "Test message"
        assert result.event_data["message_id"] == "123"
        assert result.user_id == "user123"
        assert result.attachments == []
        assert result.timestamp == mock_telegram_message.date

    def test_from_message_with_caption(self, mock_messages_sqlalchemy, mock_telegram_message):
        """Test creating ChatEvent from message with caption."""
        mock_telegram_message.text = None
        mock_telegram_message.caption = "Photo caption"
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        result = ChatEvent.from_message(mock_messages_sqlalchemy, [])

        assert result.event_type == "message"
        assert result.event_data["text"] == "Photo caption"

    def test_from_message_with_reasoning(self, mock_messages_sqlalchemy, mock_telegram_message):
        """Test creating ChatEvent from message with reasoning."""
        mock_messages_sqlalchemy.reasoning = "Bot reasoning"
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        result = ChatEvent.from_message(mock_messages_sqlalchemy, [])

        assert result.event_data["reasoning"] == "Bot reasoning"

    def test_from_message_reaction(self, mock_messages_sqlalchemy):
        """Test creating ChatEvent from message reaction."""
        # Create mock reaction update
        mock_reaction_update = type("MockReactionUpdate", (), {})()
        mock_reaction_update.message_id = 123
        mock_reaction_update.date = mock_messages_sqlalchemy.telegram_object.date

        # Create mock emoji reaction
        mock_emoji_reaction = type("MockReaction", (), {})()
        mock_emoji_reaction.type = telegram.constants.ReactionType.EMOJI
        mock_emoji_reaction.emoji = "👍"

        mock_reaction_update.new_reaction = [mock_emoji_reaction]

        mock_messages_sqlalchemy.message_type = "MessageReactionUpdated"
        mock_messages_sqlalchemy.user_id = "12345"  # User ID is required for reaction events
        mock_messages_sqlalchemy.telegram_object = mock_reaction_update

        result = ChatEvent.from_message(mock_messages_sqlalchemy, [])

        assert result.event_type == "reaction"
        assert result.event_data["emojis"] == "👍"
        assert result.event_data["to_message_id"] == "123"
        assert result.user_id == "12345"

    def test_from_context(self, mock_context_sqlalchemy):
        """Test creating ChatEvent from context."""
        result = ChatEvent.from_context(mock_context_sqlalchemy)

        assert result.event_type == "prior_conversation_summary"  # SESSION maps to this
        assert result.event_data["content"] == "Test context content"
        assert result.timestamp == mock_context_sqlalchemy.created_at
        assert result.user_id is None
        assert result.attachments == []

    def test_from_context_personality_type(self, mock_context_sqlalchemy):
        """Test creating ChatEvent from personality context."""
        mock_context_sqlalchemy.type = ContextType.PERSONALITY.value

        result = ChatEvent.from_context(mock_context_sqlalchemy)

        assert result.event_type == "switch_personality"

    def test_to_model_message_user(self, mock_chat_event_message, frozen_time):
        """Test converting user ChatEvent to model message."""
        chat_event = mock_chat_event_message(text="User input", user_id="user123")

        result = chat_event.to_model_message("bot456", frozen_time)

        assert_model_message_format(result, pydantic_ai.messages.ModelRequest)

        # Check content structure
        content = result.parts[0].content
        content_dict = assert_json_content_structure(content, ["timestamp", "event_type", "text", "message_id"])

        assert content_dict["event_type"] == "message"
        assert content_dict["text"] == "User input"
        assert "seconds ago" in content_dict["timestamp"]

    def test_to_model_message_bot(self, mock_chat_event_message, frozen_time):
        """Test converting bot ChatEvent to model message."""
        chat_event = mock_chat_event_message(text="Bot response", user_id="bot456")

        result = chat_event.to_model_message("bot456", frozen_time)

        assert_model_message_format(result, pydantic_ai.messages.ModelResponse)

        # Check content structure
        content = result.parts[0].content
        assert_json_content_structure(content, ["timestamp", "event_type", "text", "message_id"])

    def test_to_model_message_with_media(self, mock_chat_event_message, mock_media_files, frozen_time):
        """Test converting ChatEvent with media attachments."""
        media = mock_media_files(count=1, mime_type="image/png")
        chat_event = mock_chat_event_message(text="Image message", user_id="user123", attachments=[media])

        result = chat_event.to_model_message("bot456", frozen_time)

        assert len(result.parts[0].content) == 2  # JSON + binary content
        assert isinstance(result.parts[0].content[1], pydantic_ai.BinaryContent)
        assert result.parts[0].content[1].media_type == "image/png"

    def test_to_model_message_context_event(self, mock_chat_event_context, frozen_time):
        """Test converting context ChatEvent to model message."""
        chat_event = mock_chat_event_context(content="Prior conversation")

        result = chat_event.to_model_message("bot456", frozen_time)

        assert_model_message_format(result, pydantic_ai.messages.ModelResponse)

    def test_attachments_validation_message_event(
        self, mock_messages_sqlalchemy, mock_telegram_message, mock_media_files
    ):
        """Test that attachments are allowed for message events."""
        media = mock_media_files(count=1)
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        # Should not raise validation error
        result = ChatEvent.from_message(mock_messages_sqlalchemy, [media])
        assert len(result.attachments) == 1

    def test_attachments_validation_context_event(self, mock_context_sqlalchemy):
        """Test that attachments are not allowed for context events."""

        mock_file = MagicMock(spec=MediaFiles)

        with pytest.raises(ValueError, match="Attachments are only allowed for message events"):
            ChatEvent(
                timestamp=mock_context_sqlalchemy.created_at,
                event_type="prior_conversation_summary",
                event_data={"content": "test"},
                attachments=[mock_file],
                user_id=None,
            )

    def test_user_id_validation_message_event(self, mock_context_sqlalchemy):
        """Test that user_id is required for message events."""
        with pytest.raises(ValueError, match="User ID must be provided for message and reaction events"):
            ChatEvent(
                timestamp=mock_context_sqlalchemy.created_at,
                event_type="message",
                event_data={"text": "test"},
                attachments=[],
                user_id=None,
            )

    def test_user_id_validation_context_event(self, mock_context_sqlalchemy):
        """Test that user_id is allowed for context events (e.g., button actions)."""
        # This should not raise an error - user_id is now allowed for context events
        event = ChatEvent(
            timestamp=mock_context_sqlalchemy.created_at,
            event_type="prior_conversation_summary",
            event_data={"content": "test"},
            attachments=[],
            user_id="user123",
        )
        assert event.user_id == "user123"

    def test_unsupported_message_type(self, mock_messages_sqlalchemy, mock_telegram_message):
        """Test error for unsupported message types."""
        mock_messages_sqlalchemy.message_type = "UnsupportedType"
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        with pytest.raises(TypeError, match="Unsupported message type"):
            ChatEvent.from_message(mock_messages_sqlalchemy, [])

    def test_to_model_message_with_text_media(self, mock_chat_event_message, mock_media_files, frozen_time):
        """Test converting ChatEvent with text file attachments."""
        # Create a text file attachment
        text_media = mock_media_files(count=1, mime_type="text/plain")
        text_media.bytes_data = b"This is a test text file content"

        chat_event = mock_chat_event_message(text="Message with text file", user_id="user123", attachments=[text_media])

        result = chat_event.to_model_message("bot456", frozen_time)

        assert len(result.parts[0].content) == 2  # JSON + decoded text content
        assert result.parts[0].content[1] == "This is a test text file content"

    def test_to_model_message_with_multiple_text_media(self, mock_chat_event_message, mock_media_files, frozen_time):
        """Test converting ChatEvent with multiple text file attachments."""
        # Create multiple text file attachments with different MIME types
        text_media1 = mock_media_files(count=1, mime_type="text/plain")
        text_media1.bytes_data = b"First text file"

        text_media2 = mock_media_files(count=1, mime_type="text/csv")
        text_media2.bytes_data = b"name,age\nJohn,30"

        chat_event = mock_chat_event_message(
            text="Message with multiple text files", user_id="user123", attachments=[text_media1, text_media2]
        )

        result = chat_event.to_model_message("bot456", frozen_time)

        assert len(result.parts[0].content) == 3  # JSON + 2 decoded text contents
        assert result.parts[0].content[1] == "First text file"
        assert result.parts[0].content[2] == "name,age\nJohn,30"

    def test_to_model_message_with_mixed_media_types(self, mock_chat_event_message, mock_media_files, frozen_time):
        """Test converting ChatEvent with mixed media types (image, text, PDF)."""
        # Create different types of media
        image_media = mock_media_files(count=1, mime_type="image/png")

        text_media = mock_media_files(count=1, mime_type="text/html")
        text_media.bytes_data = b"<html><body>Test HTML content</body></html>"

        pdf_media = mock_media_files(count=1, mime_type="application/pdf")

        chat_event = mock_chat_event_message(
            text="Message with mixed media types", user_id="user123", attachments=[image_media, text_media, pdf_media]
        )

        result = chat_event.to_model_message("bot456", frozen_time)

        # Should have JSON + image binary + decoded text + PDF binary
        assert len(result.parts[0].content) == 4
        # First is JSON string
        assert isinstance(result.parts[0].content[0], str)
        # Second is binary content (image)
        assert isinstance(result.parts[0].content[1], pydantic_ai.BinaryContent)
        assert result.parts[0].content[1].media_type == "image/png"
        # Third is decoded text
        assert result.parts[0].content[2] == "<html><body>Test HTML content</body></html>"
        # Fourth is binary content (PDF)
        assert isinstance(result.parts[0].content[3], pydantic_ai.BinaryContent)
        assert result.parts[0].content[3].media_type == "application/pdf"

    def test_to_model_message_with_text_media_utf8_decoding(
        self, mock_chat_event_message, mock_media_files, frozen_time
    ):
        """Test text media with UTF-8 characters is properly decoded."""
        text_media = mock_media_files(count=1, mime_type="text/plain")
        text_media.bytes_data = "Hello 世界! 🌍".encode()

        chat_event = mock_chat_event_message(
            text="Message with UTF-8 text", user_id="user123", attachments=[text_media]
        )

        result = chat_event.to_model_message("bot456", frozen_time)

        assert len(result.parts[0].content) == 2
        assert result.parts[0].content[1] == "Hello 世界! 🌍"

    def test_to_model_message_with_empty_text_media(self, mock_chat_event_message, mock_media_files, frozen_time):
        """Test text media with empty content."""
        text_media = mock_media_files(count=1, mime_type="text/plain")
        text_media.bytes_data = b""

        chat_event = mock_chat_event_message(
            text="Message with empty text file", user_id="user123", attachments=[text_media]
        )

        result = chat_event.to_model_message("bot456", frozen_time)

        assert len(result.parts[0].content) == 2
        assert not result.parts[0].content[1]

    def test_to_model_message_with_non_openai_google_supported_text_media(
        self, mock_chat_event_message, mock_media_files, frozen_time
    ):
        """Test that non-OpenAI/Google supported text media is filtered out."""
        # Create a text file that is not OpenAI/Google supported
        text_media = mock_media_files(count=1, mime_type="text/plain", is_openai_google_supported=False)
        text_media.bytes_data = b"This should not appear"

        chat_event = mock_chat_event_message(
            text="Message with unsupported text file", user_id="user123", attachments=[text_media]
        )

        result = chat_event.to_model_message("bot456", frozen_time)

        # Should only have the JSON content, no text content
        # When there's only one content item, it's returned as a string, not a list
        assert isinstance(result.parts[0].content, str)
        # Verify it's just the JSON and doesn't contain the text file content
        json.loads(result.parts[0].content)
        assert "This should not appear" not in result.parts[0].content

    def test_to_model_message_with_unsupported_mime_types(self, mock_chat_event_message, mock_media_files, frozen_time):
        """Test media files with unsupported MIME types are skipped."""
        # Create media files with various MIME types, including some unsupported ones
        text_media = mock_media_files(count=1, mime_type="text/plain")
        text_media.bytes_data = b"Text content"

        # Unsupported type
        video_media = mock_media_files(count=1, mime_type="video/mp4", is_openai_google_supported=False)
        # Now supported with OpenAI/Google models
        audio_media = mock_media_files(count=1, mime_type="audio/wav")

        chat_event = mock_chat_event_message(
            text="Message with mixed supported/unsupported media",
            user_id="user123",
            attachments=[text_media, video_media, audio_media],
        )

        result = chat_event.to_model_message("bot456", frozen_time)

        # Should have JSON + text content + audio content
        # Video files should be skipped since they don't match any condition
        # Audio files are now supported with OpenAI/Google models
        assert len(result.parts[0].content) == 3
        assert result.parts[0].content[1] == "Text content"

    def test_to_model_message_system_user_treated_as_bot(self, mock_chat_event_message, frozen_time):
        """Test that system user messages are treated as bot responses (ModelResponse)."""
        chat_event = mock_chat_event_message(text="System message", user_id=SYSTEM_USER_ID)

        result = chat_event.to_model_message("bot456", frozen_time)

        # System user should be treated as bot response
        assert_model_message_format(result, pydantic_ai.messages.ModelResponse)

        # Check content structure
        content = result.parts[0].content
        assert_json_content_structure(content, ["timestamp", "event_type", "text", "message_id"])

    def test_to_model_message_bot_and_system_filtering(self, mock_chat_event_message, frozen_time):
        """Test that both bot_id and 'system' are filtered from user messages."""
        # Test bot_id filtering (existing behavior)
        bot_event = mock_chat_event_message(text="Bot message", user_id="bot456")
        bot_result = bot_event.to_model_message("bot456", frozen_time)
        assert_model_message_format(bot_result, pydantic_ai.messages.ModelResponse)

        # Test system filtering (new behavior)
        system_event = mock_chat_event_message(text="System message", user_id=SYSTEM_USER_ID)
        system_result = system_event.to_model_message("bot456", frozen_time)
        assert_model_message_format(system_result, pydantic_ai.messages.ModelResponse)

        # Test regular user still becomes ModelRequest
        user_event = mock_chat_event_message(text="User message", user_id="user123")
        user_result = user_event.to_model_message("bot456", frozen_time)
        assert_model_message_format(user_result, pydantic_ai.messages.ModelRequest)

    def test_to_model_message_system_with_different_bot_id(self, mock_chat_event_message, frozen_time):
        """Test that system user is treated as bot response regardless of bot_id."""
        chat_event = mock_chat_event_message(text="System message", user_id=SYSTEM_USER_ID)

        # Use a different bot_id than SYSTEM_USER_ID
        result = chat_event.to_model_message("different_bot_id", frozen_time)

        # System should still be treated as bot response
        assert_model_message_format(result, pydantic_ai.messages.ModelResponse)

    def test_from_message_with_reply_keyboard_markup(self, mock_messages_sqlalchemy, mock_telegram_message):
        """Test creating ChatEvent from message with ReplyKeyboardMarkup."""
        # Create mock keyboard buttons
        button1 = telegram.KeyboardButton("Option 1")
        button2 = telegram.KeyboardButton("Option 2")
        button3 = "Option 3"  # Non-KeyboardButton object

        # Create keyboard markup with multiple rows
        keyboard = [[button1, button2], [button3]]
        reply_markup = telegram.ReplyKeyboardMarkup(keyboard)

        mock_telegram_message.reply_markup = reply_markup
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        result = ChatEvent.from_message(mock_messages_sqlalchemy, [])

        assert result.event_type == "message"
        assert "keyboard_options" in result.event_data
        assert result.event_data["keyboard_options"] == ["Option 1", "Option 2", "Option 3"]

    def test_from_message_with_reply_keyboard_markup_empty(self, mock_messages_sqlalchemy, mock_telegram_message):
        """Test creating ChatEvent from message with empty ReplyKeyboardMarkup."""
        # Create empty keyboard markup
        keyboard = []
        reply_markup = telegram.ReplyKeyboardMarkup(keyboard)

        mock_telegram_message.reply_markup = reply_markup
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        result = ChatEvent.from_message(mock_messages_sqlalchemy, [])

        assert result.event_type == "message"
        assert "keyboard_options" in result.event_data
        assert result.event_data["keyboard_options"] == []

    def test_from_message_with_reply_keyboard_markup_mixed_types(self, mock_messages_sqlalchemy, mock_telegram_message):
        """Test creating ChatEvent from message with ReplyKeyboardMarkup containing mixed button types."""
        # Create keyboard with KeyboardButton objects and other types
        keyboard_button = telegram.KeyboardButton("Keyboard Button")
        string_button = "String Button"
        custom_button = type("CustomButton", (), {})()
        custom_button.text = "Custom Button"  # Custom button with text attribute

        keyboard = [[keyboard_button, string_button, custom_button]]
        reply_markup = telegram.ReplyKeyboardMarkup(keyboard)

        mock_telegram_message.reply_markup = reply_markup
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        result = ChatEvent.from_message(mock_messages_sqlalchemy, [])

        assert result.event_type == "message"
        assert "keyboard_options" in result.event_data
        # KeyboardButton should use .text, others should be str() converted
        expected_options = ["Keyboard Button", "String Button", str(custom_button)]
        assert result.event_data["keyboard_options"] == expected_options

    def test_from_message_with_inline_keyboard_markup(self, mock_messages_sqlalchemy, mock_telegram_message):
        """Test creating ChatEvent from message with InlineKeyboardMarkup."""
        # Create mock inline keyboard buttons
        button1 = telegram.InlineKeyboardButton(text="Button 1", callback_data="callback_1")
        button2 = telegram.InlineKeyboardButton(text="Button 2", callback_data="callback_2")
        button3 = telegram.InlineKeyboardButton(text="Button 3", callback_data="callback_3")

        # Create inline keyboard markup with multiple rows
        keyboard = [[button1, button2], [button3]]
        inline_markup = telegram.InlineKeyboardMarkup(keyboard)

        mock_telegram_message.reply_markup = inline_markup
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        result = ChatEvent.from_message(mock_messages_sqlalchemy, [])

        assert result.event_type == "message"
        assert "message_buttons" in result.event_data
        expected_buttons = [
            {"text": "Button 1", "callback_data": "callback_1"},
            {"text": "Button 2", "callback_data": "callback_2"},
            {"text": "Button 3", "callback_data": "callback_3"},
        ]
        assert result.event_data["message_buttons"] == expected_buttons

    def test_from_message_with_inline_keyboard_markup_empty(self, mock_messages_sqlalchemy, mock_telegram_message):
        """Test creating ChatEvent from message with empty InlineKeyboardMarkup."""
        # Create empty inline keyboard markup
        keyboard = []
        inline_markup = telegram.InlineKeyboardMarkup(keyboard)

        mock_telegram_message.reply_markup = inline_markup
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        result = ChatEvent.from_message(mock_messages_sqlalchemy, [])

        assert result.event_type == "message"
        assert "message_buttons" in result.event_data
        assert result.event_data["message_buttons"] == []

    def test_from_message_with_inline_keyboard_markup_no_callback_data(self, mock_messages_sqlalchemy, mock_telegram_message):
        """Test creating ChatEvent from message with InlineKeyboardMarkup buttons without callback_data."""
        # Create inline keyboard buttons with and without callback_data
        button1 = telegram.InlineKeyboardButton(text="Button 1", callback_data="callback_1")
        button2 = telegram.InlineKeyboardButton(text="Button 2", url="https://example.com")  # No callback_data
        button3 = telegram.InlineKeyboardButton(text="Button 3", callback_data=None)  # Explicit None

        keyboard = [[button1], [button2], [button3]]
        inline_markup = telegram.InlineKeyboardMarkup(keyboard)

        mock_telegram_message.reply_markup = inline_markup
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        result = ChatEvent.from_message(mock_messages_sqlalchemy, [])

        assert result.event_type == "message"
        assert "message_buttons" in result.event_data
        expected_buttons = [
            {"text": "Button 1", "callback_data": "callback_1"},
            {"text": "Button 2", "callback_data": None},  # url button has no callback_data
            {"text": "Button 3", "callback_data": None},  # explicit None
        ]
        assert result.event_data["message_buttons"] == expected_buttons

    def test_from_message_with_single_row_inline_keyboard(self, mock_messages_sqlalchemy, mock_telegram_message):
        """Test creating ChatEvent from message with single row InlineKeyboardMarkup."""
        # Create inline keyboard with single row
        button1 = telegram.InlineKeyboardButton(text="Yes", callback_data="yes")
        button2 = telegram.InlineKeyboardButton(text="No", callback_data="no")

        keyboard = [[button1, button2]]  # Single row with two buttons
        inline_markup = telegram.InlineKeyboardMarkup(keyboard)

        mock_telegram_message.reply_markup = inline_markup
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        result = ChatEvent.from_message(mock_messages_sqlalchemy, [])

        assert result.event_type == "message"
        assert "message_buttons" in result.event_data
        expected_buttons = [
            {"text": "Yes", "callback_data": "yes"},
            {"text": "No", "callback_data": "no"},
        ]
        assert result.event_data["message_buttons"] == expected_buttons

    def test_from_message_without_reply_markup(self, mock_messages_sqlalchemy, mock_telegram_message):
        """Test creating ChatEvent from message without reply_markup (baseline test)."""
        # Ensure no reply_markup is set
        mock_telegram_message.reply_markup = None
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        result = ChatEvent.from_message(mock_messages_sqlalchemy, [])

        assert result.event_type == "message"
        assert "keyboard_options" not in result.event_data
        assert "message_buttons" not in result.event_data
        # Should still have basic message data
        assert "text" in result.event_data
        assert "message_id" in result.event_data
