# ruff: noqa: PLC2701

"""Tests for agent utility functions."""

import json
from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pydantic_ai
import pytest
import telegram
from pydantic_ai import messages

from areyouok_telegram.jobs.utils import _telegram_message_to_model_message
from areyouok_telegram.jobs.utils import _telegram_reaction_to_model_message
from areyouok_telegram.jobs.utils import convert_telegram_message_to_model_message
from areyouok_telegram.llms.utils import telegram_message_to_dict


class TestMediaFileProcessing:
    """Test suite for media file processing in _telegram_message_to_model_message."""

    @pytest.mark.asyncio
    async def test_message_with_image_media(self):
        """Test processing message with image media files."""
        # Create mock message
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 123
        mock_message.text = "Check out this image"
        mock_message.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123456

        # Mock image media file
        image_file = MagicMock()
        image_file.mime_type = "image/png"
        image_file.bytes_data = b"fake_image_data"

        with patch("areyouok_telegram.data.MediaFiles.get_by_message_id", new_callable=AsyncMock) as mock_get_media:
            mock_get_media.return_value = [image_file]

            result = await _telegram_message_to_model_message(None, mock_message, datetime.now(UTC), is_user=True)

            # Verify result is ModelRequest with image content
            assert isinstance(result, messages.ModelRequest)
            assert len(result.parts[0].content) == 2  # JSON + image
            assert isinstance(result.parts[0].content[1], pydantic_ai.BinaryContent)
            assert result.parts[0].content[1].media_type == "image/png"
            assert result.parts[0].content[1].data == b"fake_image_data"

    @pytest.mark.asyncio
    async def test_message_with_pdf_media(self):
        """Test processing message with PDF media files."""
        # Create mock message
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 456
        mock_message.text = "Here's the PDF"
        mock_message.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123456

        # Mock PDF media file
        pdf_file = MagicMock()
        pdf_file.mime_type = "application/pdf"
        pdf_file.bytes_data = b"fake_pdf_data"

        with patch("areyouok_telegram.data.MediaFiles.get_by_message_id", new_callable=AsyncMock) as mock_get_media:
            mock_get_media.return_value = [pdf_file]

            result = await _telegram_message_to_model_message(None, mock_message, datetime.now(UTC), is_user=True)

            # Verify result includes PDF as binary content
            assert isinstance(result, messages.ModelRequest)
            assert len(result.parts[0].content) == 2  # JSON + PDF
            assert isinstance(result.parts[0].content[1], pydantic_ai.BinaryContent)
            assert result.parts[0].content[1].media_type == "application/pdf"
            assert result.parts[0].content[1].data == b"fake_pdf_data"

    @pytest.mark.asyncio
    async def test_message_with_text_file_media(self):
        """Test processing message with text file media."""
        # Create mock message
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 789
        mock_message.text = "Text file attached"
        mock_message.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123456

        # Mock text media file
        text_file = MagicMock()
        text_file.mime_type = "text/plain"
        text_file.bytes_data = b"Hello from text file"

        with patch("areyouok_telegram.data.MediaFiles.get_by_message_id", new_callable=AsyncMock) as mock_get_media:
            mock_get_media.return_value = [text_file]

            result = await _telegram_message_to_model_message(None, mock_message, datetime.now(UTC), is_user=True)

            # Verify result includes text content as string
            assert isinstance(result, messages.ModelRequest)
            assert len(result.parts[0].content) == 2  # JSON + text
            assert isinstance(result.parts[0].content[1], str)
            assert result.parts[0].content[1] == "Hello from text file"

    @pytest.mark.asyncio
    async def test_message_with_multiple_mixed_media(self):
        """Test processing message with multiple media types."""
        # Create mock message
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 999
        mock_message.text = "Multiple files"
        mock_message.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123456

        # Mock multiple media files
        image_file = MagicMock()
        image_file.mime_type = "image/jpeg"
        image_file.bytes_data = b"image_data"

        text_file = MagicMock()
        text_file.mime_type = "text/markdown"
        text_file.bytes_data = b"# Markdown content"

        video_file = MagicMock()
        video_file.mime_type = "video/mp4"
        video_file.bytes_data = b"video_data"

        with patch("areyouok_telegram.data.MediaFiles.get_by_message_id", new_callable=AsyncMock) as mock_get_media:
            mock_get_media.return_value = [image_file, text_file, video_file]

            result = await _telegram_message_to_model_message(None, mock_message, datetime.now(UTC), is_user=True)

            # Verify only supported media is included (image + text, not video)
            assert isinstance(result, messages.ModelRequest)
            assert len(result.parts[0].content) == 3  # JSON + image + text

            # Check image content
            assert isinstance(result.parts[0].content[1], pydantic_ai.BinaryContent)
            assert result.parts[0].content[1].media_type == "image/jpeg"

            # Check text content
            assert isinstance(result.parts[0].content[2], str)
            assert result.parts[0].content[2] == "# Markdown content"

    @pytest.mark.asyncio
    async def test_message_with_unsupported_media_only(self):
        """Test processing message with only unsupported media types."""
        # Create mock message
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 555
        mock_message.text = "Video attached"
        mock_message.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123456

        # Mock unsupported media file
        video_file = MagicMock()
        video_file.mime_type = "video/mp4"
        video_file.bytes_data = b"video_data"

        with patch("areyouok_telegram.data.MediaFiles.get_by_message_id", new_callable=AsyncMock) as mock_get_media:
            mock_get_media.return_value = [video_file]

            result = await _telegram_message_to_model_message(None, mock_message, datetime.now(UTC), is_user=True)

            # Verify only JSON content is included (unsupported media is skipped)
            assert isinstance(result, messages.ModelRequest)
            assert isinstance(result.parts[0].content, str)  # Only JSON, no list


class TestTelegramMessageToDict:
    """Test suite for telegram_message_to_dict function."""

    def test_telegram_message_to_dict(self):
        """Test converting a Telegram message to dict."""
        # Create mock message
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 456
        mock_message.text = "Hello, I need help"
        mock_message.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_message.caption = None  # No caption for text messages

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)  # 5 minutes later

        # Convert to dict
        result = telegram_message_to_dict(mock_message, ts_reference)

        # Verify result
        assert result["text"] == "Hello, I need help"
        assert result["message_id"] == "456"
        assert result["timestamp"] == "300 seconds ago"  # 5 minutes = 300 seconds

    def test_telegram_reaction_to_dict(self):
        """Test converting a Telegram reaction to dict."""
        # Create mock reaction
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 789
        mock_reaction.date = datetime(2025, 1, 15, 10, 32, 0, tzinfo=UTC)

        # Mock reactions
        emoji_reaction1 = MagicMock()
        emoji_reaction1.type = telegram.constants.ReactionType.EMOJI
        emoji_reaction1.emoji = "❤️"

        emoji_reaction2 = MagicMock()
        emoji_reaction2.type = telegram.constants.ReactionType.EMOJI
        emoji_reaction2.emoji = "👍"

        mock_reaction.new_reaction = (emoji_reaction1, emoji_reaction2)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)  # 3 minutes later

        # Convert to dict
        result = telegram_message_to_dict(mock_reaction, ts_reference)

        # Verify result
        assert result["reaction"] == "❤️, 👍"
        assert result["to_message_id"] == "789"
        assert result["timestamp"] == "180 seconds ago"  # 3 minutes = 180 seconds

    def test_telegram_reaction_with_non_emoji_filtered(self):
        """Test that non-emoji reactions are filtered out."""
        # Create mock reaction
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 789
        mock_reaction.date = datetime(2025, 1, 15, 10, 32, 0, tzinfo=UTC)

        # Mock mixed reactions
        emoji_reaction = MagicMock()
        emoji_reaction.type = telegram.constants.ReactionType.EMOJI
        emoji_reaction.emoji = "❤️"

        custom_reaction = MagicMock()
        custom_reaction.type = telegram.constants.ReactionType.CUSTOM_EMOJI
        custom_reaction.custom_emoji_id = "custom_123"

        mock_reaction.new_reaction = (emoji_reaction, custom_reaction)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)

        # Convert to dict
        result = telegram_message_to_dict(mock_reaction, ts_reference)

        # Verify only emoji reaction is included
        assert result["reaction"] == "❤️"

    def test_unsupported_message_type_raises_error(self):
        """Test that unsupported message types raise TypeError."""
        # Create mock object that's not Message or MessageReactionUpdated
        mock_unsupported = MagicMock()

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)

        # Should raise TypeError
        with pytest.raises(TypeError) as exc_info:
            telegram_message_to_dict(mock_unsupported, ts_reference)

        assert "Unsupported message type" in str(exc_info.value)


@pytest.fixture
def mock_no_media_files():
    """Mock MediaFiles.get_by_message_id to return empty list."""
    with patch("areyouok_telegram.data.MediaFiles.get_by_message_id", return_value=[]):
        yield


@pytest.mark.usefixtures("mock_no_media_files")
class TestTelegramMessageToModelMessage:
    """Test suite for _telegram_message_to_model_message function."""

    @pytest.mark.asyncio
    async def test_user_message_to_model_request(self, mock_async_database_session):
        """Test converting a user message to ModelRequest."""
        # Create mock message
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 456
        mock_message.text = "Hello, I need help"
        mock_message.from_user = MagicMock()
        mock_message.from_user.id = 123456789
        mock_message.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123456

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)  # 5 minutes later

        # Convert message
        result = await _telegram_message_to_model_message(
            mock_async_database_session, mock_message, ts_reference, is_user=True
        )

        # Verify result is ModelRequest
        assert isinstance(result, messages.ModelRequest)
        assert len(result.parts) == 1
        assert isinstance(result.parts[0], messages.UserPromptPart)

        # Check content
        content = json.loads(result.parts[0].content)
        assert content["text"] == "Hello, I need help"
        assert content["message_id"] == "456"
        assert content["timestamp"] == "300 seconds ago"

    @pytest.mark.asyncio
    async def test_bot_message_to_model_response(self, mock_async_database_session):
        """Test converting a bot message to ModelResponse."""
        # Create mock message
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 789
        mock_message.text = "I understand you need help"
        mock_message.from_user = MagicMock()
        mock_message.from_user.id = 999999999  # Bot ID
        mock_message.date = datetime(2025, 1, 15, 10, 32, 0, tzinfo=UTC)
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123456

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)  # 3 minutes later

        # Convert message (is_user=False for bot messages)
        result = await _telegram_message_to_model_message(
            mock_async_database_session, mock_message, ts_reference, is_user=False
        )

        # Verify result is ModelResponse
        assert isinstance(result, messages.ModelResponse)
        assert len(result.parts) == 1
        assert isinstance(result.parts[0], messages.TextPart)

        # Check content
        content_data = json.loads(result.parts[0].content)
        assert content_data["text"] == "I understand you need help"
        assert content_data["message_id"] == "789"
        assert content_data["timestamp"] == "180 seconds ago"

    @pytest.mark.asyncio
    async def test_message_from_none_user(self, mock_async_database_session):
        """Test handling message with None from_user."""
        # Create mock message with None from_user
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 999
        mock_message.text = "Anonymous message"
        mock_message.from_user = None  # No user info
        mock_message.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123456

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)

        # Convert message as user message
        result = await _telegram_message_to_model_message(
            mock_async_database_session, mock_message, ts_reference, is_user=True
        )

        # Should still return valid ModelRequest
        assert isinstance(result, messages.ModelRequest)

    @pytest.mark.asyncio
    async def test_timing_calculation_accuracy(self, mock_async_database_session):
        """Test accurate timestamp calculation in various scenarios."""
        # Create mock message
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 123
        mock_message.text = "Test timing"
        mock_message.date = datetime(2025, 1, 15, 10, 30, 45, tzinfo=UTC)
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123456

        # Test various time differences
        test_cases = [
            (datetime(2025, 1, 15, 10, 30, 45, tzinfo=UTC), "0 seconds ago"),  # Same time
            (datetime(2025, 1, 15, 10, 31, 45, tzinfo=UTC), "60 seconds ago"),  # 1 minute
            (datetime(2025, 1, 15, 11, 30, 45, tzinfo=UTC), "3600 seconds ago"),  # 1 hour
        ]

        for ts_ref, expected_timestamp in test_cases:
            result = await _telegram_message_to_model_message(
                mock_async_database_session, mock_message, ts_ref, is_user=True
            )
            content = json.loads(result.parts[0].content)
            assert content["timestamp"] == expected_timestamp


class TestTelegramReactionToModelMessage:
    """Test suite for _telegram_reaction_to_model_message function."""

    @pytest.mark.asyncio
    async def test_user_reaction_to_model_request(self, mock_async_database_session):  # noqa: ARG002
        """Test converting a user reaction to ModelRequest."""
        # Create mock reaction
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 456
        mock_reaction.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_reaction.user = MagicMock()
        mock_reaction.user.id = 123456789  # User ID

        # Mock emoji reaction
        emoji_reaction = MagicMock()
        emoji_reaction.type = telegram.constants.ReactionType.EMOJI
        emoji_reaction.emoji = "❤️"
        mock_reaction.new_reaction = (emoji_reaction,)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)  # 5 minutes later

        # Convert reaction
        result = await _telegram_reaction_to_model_message(mock_reaction, ts_reference, is_user=True)

        # Verify result is ModelRequest
        assert isinstance(result, messages.ModelRequest)
        assert len(result.parts) == 1
        assert isinstance(result.parts[0], messages.UserPromptPart)

        # Check content
        content = json.loads(result.parts[0].content)
        assert content["reaction"] == "❤️"
        assert content["to_message_id"] == "456"
        assert content["timestamp"] == "300 seconds ago"

    @pytest.mark.asyncio
    async def test_bot_reaction_to_model_response(self, mock_async_database_session):  # noqa: ARG002
        """Test converting a bot reaction to ModelResponse."""
        # Create mock reaction from bot
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 789
        mock_reaction.date = datetime(2025, 1, 15, 10, 32, 0, tzinfo=UTC)
        mock_reaction.user = MagicMock()
        mock_reaction.user.id = 999999999  # Bot ID

        # Mock emoji reaction
        emoji_reaction = MagicMock()
        emoji_reaction.type = telegram.constants.ReactionType.EMOJI
        emoji_reaction.emoji = "👍"
        mock_reaction.new_reaction = (emoji_reaction,)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)  # 3 minutes later

        # Convert reaction (is_user=False for bot)
        result = await _telegram_reaction_to_model_message(mock_reaction, ts_reference, is_user=False)

        # Verify result is ModelResponse
        assert isinstance(result, messages.ModelResponse)
        assert len(result.parts) == 1
        assert isinstance(result.parts[0], messages.TextPart)

        # Check content
        content_data = json.loads(result.parts[0].content)
        assert content_data["reaction"] == "👍"
        assert content_data["to_message_id"] == "789"
        assert content_data["timestamp"] == "180 seconds ago"

    @pytest.mark.asyncio
    async def test_multiple_emoji_reactions(self, mock_async_database_session):  # noqa: ARG002
        """Test handling multiple emoji reactions."""
        # Create mock reaction with multiple emojis
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 123
        mock_reaction.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Multiple emoji reactions
        emoji1 = MagicMock()
        emoji1.type = telegram.constants.ReactionType.EMOJI
        emoji1.emoji = "❤️"

        emoji2 = MagicMock()
        emoji2.type = telegram.constants.ReactionType.EMOJI
        emoji2.emoji = "🔥"

        emoji3 = MagicMock()
        emoji3.type = telegram.constants.ReactionType.EMOJI
        emoji3.emoji = "👏"

        mock_reaction.new_reaction = (emoji1, emoji2, emoji3)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Convert reaction
        result = await _telegram_reaction_to_model_message(mock_reaction, ts_reference, is_user=True)

        # Check content
        content = json.loads(result.parts[0].content)
        assert content["reaction"] == "❤️, 🔥, 👏"

    @pytest.mark.asyncio
    async def test_non_emoji_reactions_filtered(self, mock_async_database_session):  # noqa: ARG002
        """Test that non-emoji reactions are filtered out."""
        # Create mock reaction with mixed types
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 456
        mock_reaction.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Mixed reaction types
        emoji_reaction = MagicMock()
        emoji_reaction.type = telegram.constants.ReactionType.EMOJI
        emoji_reaction.emoji = "❤️"

        custom_reaction = MagicMock()
        custom_reaction.type = telegram.constants.ReactionType.CUSTOM_EMOJI
        custom_reaction.custom_emoji_id = "custom_123"

        mock_reaction.new_reaction = (emoji_reaction, custom_reaction)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Convert reaction
        result = await _telegram_reaction_to_model_message(mock_reaction, ts_reference, is_user=True)

        # Check that only emoji reaction is included
        content = json.loads(result.parts[0].content)
        assert content["reaction"] == "❤️"  # Only emoji, not custom

    @pytest.mark.asyncio
    async def test_reaction_from_none_user(self, mock_async_database_session):  # noqa: ARG002
        """Test handling reaction with None user."""
        # Create mock reaction with None user
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 999
        mock_reaction.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_reaction.user = None  # No user info

        # Mock emoji reaction
        emoji_reaction = MagicMock()
        emoji_reaction.type = telegram.constants.ReactionType.EMOJI
        emoji_reaction.emoji = "👍"
        mock_reaction.new_reaction = (emoji_reaction,)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)

        # Convert reaction as user reaction
        result = await _telegram_reaction_to_model_message(mock_reaction, ts_reference, is_user=True)

        # Should still return valid ModelRequest
        assert isinstance(result, messages.ModelRequest)


@pytest.mark.usefixtures("mock_no_media_files")
class TestConvertTelegramMessageToModelMessage:
    """Test suite for convert_telegram_message_to_model_message public function."""

    @pytest.mark.asyncio
    async def test_convert_message_without_ts_reference(self, mock_async_database_session):
        """Test converting message without providing ts_reference."""
        # Create mock message
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 123
        mock_message.text = "Test message"
        mock_message.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123456

        # Convert without ts_reference (should use current time)
        result = await convert_telegram_message_to_model_message(
            mock_async_database_session, mock_message, is_user=True
        )

        # Should return valid ModelRequest
        assert isinstance(result, messages.ModelRequest)

    @pytest.mark.asyncio
    async def test_convert_reaction_with_ts_reference(self, mock_async_database_session):  # noqa: ARG002
        """Test converting reaction with ts_reference."""
        # Create mock reaction
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 456
        mock_reaction.date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Mock emoji reaction
        emoji_reaction = MagicMock()
        emoji_reaction.type = telegram.constants.ReactionType.EMOJI
        emoji_reaction.emoji = "❤️"
        mock_reaction.new_reaction = (emoji_reaction,)

        # Reference timestamp
        ts_reference = datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)

        # Convert with ts_reference
        result = await convert_telegram_message_to_model_message(
            mock_async_database_session, mock_reaction, ts_reference, is_user=False
        )

        # Should return valid ModelResponse
        assert isinstance(result, messages.ModelResponse)
        content = json.loads(result.parts[0].content)
        assert content["timestamp"] == "300 seconds ago"

    @pytest.mark.asyncio
    async def test_convert_handles_message_and_reaction_types(self, mock_async_database_session):
        """Test that convert function properly routes messages and reactions."""
        # Test with Message
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.message_id = 123
        mock_message.text = "Test"
        mock_message.date = datetime.now(UTC)
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123456

        result_message = await convert_telegram_message_to_model_message(
            mock_async_database_session, mock_message, is_user=True
        )
        assert isinstance(result_message, messages.ModelRequest)

        # Test with Reaction
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 456
        mock_reaction.date = datetime.now(UTC)
        emoji_reaction = MagicMock()
        emoji_reaction.type = telegram.constants.ReactionType.EMOJI
        emoji_reaction.emoji = "👍"
        mock_reaction.new_reaction = (emoji_reaction,)

        result_reaction = await convert_telegram_message_to_model_message(
            mock_async_database_session, mock_reaction, is_user=False
        )
        assert isinstance(result_reaction, messages.ModelResponse)
