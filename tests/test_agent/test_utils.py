# ruff: noqa: PLC2701

"""Tests for agent utility functions."""

import json
from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock

import telegram
from pydantic_ai import messages

from areyouok_telegram.agent.utils import _telegram_message_to_model_message
from areyouok_telegram.agent.utils import _telegram_reaction_to_model_message


class TestTelegramMessageToModelMessage:
    """Test suite for _telegram_message_to_model_message function."""

    def test_user_message_to_model_request(self):
        """Test converting a user message to ModelRequest."""
        # Create mock context
        mock_context = MagicMock()
        mock_context.bot.id = 999999999

        # Create mock user and message
        mock_user = MagicMock(spec=telegram.User)
        mock_user.id = 123456789  # Different from bot ID

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 456
        mock_message.text = "Hello, I need help"
        mock_message.from_user = mock_user
        mock_message.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)  # 5 minutes later

        # Convert message
        result = _telegram_message_to_model_message(mock_context, mock_message, ts_reference)

        # Verify result is ModelRequest
        assert isinstance(result, messages.ModelRequest)
        assert result.kind == "request"
        assert len(result.parts) == 1

        # Verify the content
        part = result.parts[0]
        assert isinstance(part, messages.UserPromptPart)
        assert part.part_kind == "user-prompt"
        assert part.timestamp == mock_message.date

        # Parse and verify the JSON content
        content_data = json.loads(part.content)
        assert content_data["text"] == "Hello, I need help"
        assert content_data["message_id"] == "456"
        assert content_data["timestamp"] == "300 seconds ago"  # 5 minutes = 300 seconds

    def test_bot_message_to_model_response(self):
        """Test converting a bot message to ModelResponse."""
        # Create mock context
        mock_context = MagicMock()
        mock_context.bot.id = 999999999

        # Create mock bot user and message (from bot)
        mock_bot_user = MagicMock(spec=telegram.User)
        mock_bot_user.id = 999999999  # Same as bot ID

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 789
        mock_message.text = "I understand you need help"
        mock_message.from_user = mock_bot_user
        mock_message.date = datetime(2025, 1, 15, 10, 32, 0, tzinfo=UTC)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)  # 3 minutes later

        # Convert message
        result = _telegram_message_to_model_message(mock_context, mock_message, ts_reference)

        # Verify result is ModelResponse
        assert isinstance(result, messages.ModelResponse)
        assert result.kind == "response"
        assert result.timestamp == mock_message.date
        assert len(result.parts) == 1

        # Verify the content
        part = result.parts[0]
        assert isinstance(part, messages.TextPart)
        assert part.part_kind == "text"

        # Parse and verify the JSON content
        content_data = json.loads(part.content)
        assert content_data["text"] == "I understand you need help"
        assert content_data["message_id"] == "789"
        assert content_data["timestamp"] == "180 seconds ago"  # 3 minutes = 180 seconds

    def test_message_from_none_user(self):
        """Test converting a message with no from_user (should be treated as bot)."""
        # Create mock context
        mock_context = MagicMock()
        mock_context.bot.id = 999999999

        # Create mock message with no from_user
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 321
        mock_message.text = "System message"
        mock_message.from_user = None
        mock_message.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 31, 0, tzinfo=UTC)  # 1 minute later

        # Convert message
        result = _telegram_message_to_model_message(mock_context, mock_message, ts_reference)

        # Should be treated as ModelResponse (not from user)
        assert isinstance(result, messages.ModelResponse)
        assert result.kind == "response"

    def test_timing_calculation_accuracy(self):
        """Test that timing calculations are accurate."""
        # Create mock context and message
        mock_context = MagicMock()
        mock_context.bot.id = 999999999

        mock_user = MagicMock(spec=telegram.User)
        mock_user.id = 123456789

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 100
        mock_message.text = "Test timing"
        mock_message.from_user = mock_user
        mock_message.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Test various time differences
        test_cases = [
            (datetime(2025, 1, 15, 10, 0, 30, tzinfo=UTC), "30 seconds ago"),
            (datetime(2025, 1, 15, 10, 5, 0, tzinfo=UTC), "300 seconds ago"),
            (datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC), "3600 seconds ago"),
        ]

        for ts_reference, expected_timing in test_cases:
            result = _telegram_message_to_model_message(mock_context, mock_message, ts_reference)
            content_data = json.loads(result.parts[0].content)
            assert content_data["timestamp"] == expected_timing


class TestTelegramReactionToModelMessage:
    """Test suite for _telegram_reaction_to_model_message function."""

    def test_user_reaction_to_model_request(self):
        """Test converting a user reaction to ModelRequest."""
        # Create mock context
        mock_context = MagicMock()
        mock_context.bot.id = 999999999

        # Create mock user
        mock_user = MagicMock(spec=telegram.User)
        mock_user.id = 123456789  # Different from bot ID

        # Create mock reaction types
        mock_reaction_type = MagicMock()
        mock_reaction_type.type = telegram.constants.ReactionType.EMOJI
        mock_reaction_type.emoji = "❤️"

        # Create mock reaction
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 456
        mock_reaction.user = mock_user
        mock_reaction.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_reaction.new_reaction = (mock_reaction_type,)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 32, 0, tzinfo=UTC)  # 2 minutes later

        # Convert reaction
        result = _telegram_reaction_to_model_message(mock_context, mock_reaction, ts_reference)

        # Verify result is ModelRequest
        assert isinstance(result, messages.ModelRequest)
        assert result.kind == "request"
        assert len(result.parts) == 1

        # Verify the content
        part = result.parts[0]
        assert isinstance(part, messages.UserPromptPart)
        assert part.part_kind == "user-prompt"
        assert part.timestamp == mock_reaction.date

        # Parse and verify the JSON content
        content_data = json.loads(part.content)
        assert content_data["reaction"] == "❤️"
        assert content_data["to_message_id"] == "456"
        assert content_data["timestamp"] == "120 seconds ago"  # 2 minutes = 120 seconds

    def test_bot_reaction_to_model_response(self):
        """Test converting a bot reaction to ModelResponse."""
        # Create mock context
        mock_context = MagicMock()
        mock_context.bot.id = 999999999

        # Create mock bot user
        mock_bot_user = MagicMock(spec=telegram.User)
        mock_bot_user.id = 999999999  # Same as bot ID

        # Create mock reaction types
        mock_reaction_type = MagicMock()
        mock_reaction_type.type = telegram.constants.ReactionType.EMOJI
        mock_reaction_type.emoji = "👍"

        # Create mock reaction from bot
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 789
        mock_reaction.user = mock_bot_user
        mock_reaction.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_reaction.new_reaction = (mock_reaction_type,)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 31, 30, tzinfo=UTC)  # 1.5 minutes later

        # Convert reaction
        result = _telegram_reaction_to_model_message(mock_context, mock_reaction, ts_reference)

        # Verify result is ModelResponse
        assert isinstance(result, messages.ModelResponse)
        assert result.kind == "response"
        assert result.timestamp == mock_reaction.date
        assert len(result.parts) == 1

        # Verify the content
        part = result.parts[0]
        assert isinstance(part, messages.TextPart)
        assert part.part_kind == "text"

        # Parse and verify the JSON content
        content_data = json.loads(part.content)
        assert content_data["reaction"] == "👍"
        assert content_data["to_message_id"] == "789"
        assert content_data["timestamp"] == "90 seconds ago"  # 1.5 minutes = 90 seconds

    def test_multiple_emoji_reactions(self):
        """Test converting reaction with multiple emojis."""
        # Create mock context
        mock_context = MagicMock()
        mock_context.bot.id = 999999999

        # Create mock user
        mock_user = MagicMock(spec=telegram.User)
        mock_user.id = 123456789

        # Create multiple mock reaction types
        mock_reaction_type1 = MagicMock()
        mock_reaction_type1.type = telegram.constants.ReactionType.EMOJI
        mock_reaction_type1.emoji = "❤️"

        mock_reaction_type2 = MagicMock()
        mock_reaction_type2.type = telegram.constants.ReactionType.EMOJI
        mock_reaction_type2.emoji = "🔥"

        # Create mock reaction with multiple emojis
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 123
        mock_reaction.user = mock_user
        mock_reaction.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_reaction.new_reaction = (mock_reaction_type1, mock_reaction_type2)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 30, 30, tzinfo=UTC)  # 30 seconds later

        # Convert reaction
        result = _telegram_reaction_to_model_message(mock_context, mock_reaction, ts_reference)

        # Parse and verify the JSON content
        content_data = json.loads(result.parts[0].content)
        assert content_data["reaction"] == "❤️, 🔥"  # Should be comma-separated

    def test_non_emoji_reactions_filtered(self):
        """Test that non-emoji reactions are filtered out."""
        # Create mock context
        mock_context = MagicMock()
        mock_context.bot.id = 999999999

        # Create mock user
        mock_user = MagicMock(spec=telegram.User)
        mock_user.id = 123456789

        # Create mixed reaction types (emoji and non-emoji)
        mock_emoji_reaction = MagicMock()
        mock_emoji_reaction.type = telegram.constants.ReactionType.EMOJI
        mock_emoji_reaction.emoji = "❤️"

        mock_custom_reaction = MagicMock()
        mock_custom_reaction.type = "custom_emoji"  # Not telegram.constants.ReactionType.EMOJI

        # Create mock reaction with mixed types
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 456
        mock_reaction.user = mock_user
        mock_reaction.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_reaction.new_reaction = (mock_emoji_reaction, mock_custom_reaction)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Convert reaction
        result = _telegram_reaction_to_model_message(mock_context, mock_reaction, ts_reference)

        # Parse and verify only emoji reaction is included
        content_data = json.loads(result.parts[0].content)
        assert content_data["reaction"] == "❤️"  # Only emoji, not custom

    def test_reaction_from_none_user(self):
        """Test converting reaction with no user (should be treated as bot)."""
        # Create mock context
        mock_context = MagicMock()
        mock_context.bot.id = 999999999

        # Create mock reaction type
        mock_reaction_type = MagicMock()
        mock_reaction_type.type = telegram.constants.ReactionType.EMOJI
        mock_reaction_type.emoji = "👀"

        # Create mock reaction with no user
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 789
        mock_reaction.user = None
        mock_reaction.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_reaction.new_reaction = (mock_reaction_type,)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Convert reaction
        result = _telegram_reaction_to_model_message(mock_context, mock_reaction, ts_reference)

        # Should be treated as ModelResponse (not from user)
        assert isinstance(result, messages.ModelResponse)
        assert result.kind == "response"
