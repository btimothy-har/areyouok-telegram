"""Tests for llms/utils.py."""

import json
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pydantic_ai
import pytest
import telegram
from pydantic_ai.agent import AgentRunResult

from areyouok_telegram.data import Context
from areyouok_telegram.data import MediaFiles
from areyouok_telegram.llms.utils import context_to_model_message
from areyouok_telegram.llms.utils import run_agent_with_tracking
from areyouok_telegram.llms.utils import telegram_message_to_dict
from areyouok_telegram.llms.utils import telegram_message_to_model_message


class TestRunAgentWithTracking:
    """Test the run_agent_with_tracking function."""

    @pytest.mark.asyncio
    async def test_run_agent_with_tracking_success(self):
        """Test successful agent run with tracking."""
        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_agent.run = AsyncMock()

        # Mock result
        mock_result = MagicMock(spec=AgentRunResult)
        mock_usage_data = {"tokens": 100}
        mock_result.usage.return_value = mock_usage_data
        mock_agent.run.return_value = mock_result

        # Mock database and LLMUsage
        with (
            patch("areyouok_telegram.llms.utils.async_database") as mock_async_db,
            patch("areyouok_telegram.llms.utils.LLMUsage.track_pydantic_usage", new=AsyncMock()) as mock_track,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            result = await run_agent_with_tracking(
                agent=mock_agent, chat_id="123", session_id="session123", run_kwargs={"message_history": []}
            )

        # Verify agent was called
        mock_agent.run.assert_called_once_with(message_history=[])

        # Verify tracking was called
        mock_track.assert_called_once_with(
            db_conn=mock_db_conn, chat_id="123", session_id="session123", agent=mock_agent, data=mock_usage_data
        )

        # Verify result was returned
        assert result == mock_result

    @pytest.mark.asyncio
    async def test_run_agent_with_tracking_missing_kwargs(self):
        """Test error when neither user_prompt nor message_history is provided."""
        mock_agent = MagicMock(spec=pydantic_ai.Agent)

        with pytest.raises(ValueError, match="Either 'user_prompt' or 'message_history' must be provided"):
            await run_agent_with_tracking(
                agent=mock_agent, chat_id="123", session_id="session123", run_kwargs={"other_param": "value"}
            )

    @pytest.mark.asyncio
    async def test_run_agent_with_tracking_logs_error(self):
        """Test that tracking errors are logged but don't fail the function."""
        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_agent.run = AsyncMock()

        # Mock result
        mock_result = MagicMock(spec=AgentRunResult)
        mock_result.usage.return_value = {"tokens": 100}
        mock_agent.run.return_value = mock_result

        # Mock database and LLMUsage to raise error
        with (
            patch("areyouok_telegram.llms.utils.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.llms.utils.LLMUsage.track_pydantic_usage",
                new=AsyncMock(side_effect=Exception("DB Error")),
            ),
            patch("areyouok_telegram.llms.utils.logfire.exception") as mock_log_exception,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            result = await run_agent_with_tracking(
                agent=mock_agent, chat_id="123", session_id="session123", run_kwargs={"user_prompt": "test"}
            )

        # Verify error was logged
        mock_log_exception.assert_called_once()
        log_call = mock_log_exception.call_args
        assert "Failed to log LLM usage: DB Error" in log_call[0][0]
        assert log_call.kwargs["agent"] == "test_agent"
        assert log_call.kwargs["chat_id"] == "123"
        assert log_call.kwargs["session_id"] == "session123"

        # Verify result was still returned
        assert result == mock_result


class TestTelegramMessageToDict:
    """Test the telegram_message_to_dict function."""

    def test_telegram_message_to_dict_with_text(self, frozen_time):
        """Test converting a text message to dict."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.text = "Hello world"
        mock_message.caption = None
        mock_message.message_id = 123
        mock_message.date = frozen_time - timedelta(seconds=30)

        result = telegram_message_to_dict(mock_message, ts_reference=frozen_time)

        assert result == {"text": "Hello world", "message_id": "123", "timestamp": "30 seconds ago"}

    def test_telegram_message_to_dict_with_caption(self, frozen_time):
        """Test converting a message with caption to dict."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.text = None
        mock_message.caption = "Photo caption"
        mock_message.message_id = 456
        mock_message.date = frozen_time - timedelta(minutes=5)

        result = telegram_message_to_dict(mock_message, ts_reference=frozen_time)

        assert result == {"text": "Photo caption", "message_id": "456", "timestamp": "300 seconds ago"}

    def test_telegram_message_to_dict_empty_message(self, frozen_time):
        """Test converting an empty message to dict."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.text = None
        mock_message.caption = None
        mock_message.message_id = 789
        mock_message.date = frozen_time

        result = telegram_message_to_dict(mock_message, ts_reference=frozen_time)

        assert result == {"text": "", "message_id": "789", "timestamp": "0 seconds ago"}

    def test_telegram_reaction_to_dict(self, frozen_time):
        """Test converting a reaction to dict."""
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 111
        mock_reaction.date = frozen_time - timedelta(seconds=10)

        # Mock emoji reactions
        mock_emoji_reaction = MagicMock()
        mock_emoji_reaction.type = telegram.constants.ReactionType.EMOJI
        mock_emoji_reaction.emoji = "👍"

        mock_custom_reaction = MagicMock()
        mock_custom_reaction.type = telegram.constants.ReactionType.CUSTOM_EMOJI

        mock_reaction.new_reaction = [mock_emoji_reaction, mock_custom_reaction]

        result = telegram_message_to_dict(mock_reaction, ts_reference=frozen_time)

        assert result == {"reaction": "👍", "to_message_id": "111", "timestamp": "10 seconds ago"}

    def test_telegram_message_to_dict_unsupported_type(self):
        """Test error on unsupported message type."""
        unsupported_obj = MagicMock()

        with pytest.raises(TypeError, match="Unsupported message type"):
            telegram_message_to_dict(unsupported_obj)

    def test_telegram_message_to_dict_default_reference(self):
        """Test that default reference time is used."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.text = "Test"
        mock_message.caption = None
        mock_message.message_id = 999
        mock_message.date = datetime.now(UTC) - timedelta(seconds=5)

        # Don't provide ts_reference
        result = telegram_message_to_dict(mock_message)

        # Should have a timestamp field with seconds ago
        assert "timestamp" in result
        assert "seconds ago" in result["timestamp"]


class TestContextToModelMessage:
    """Test the context_to_model_message function."""

    def test_context_to_model_message(self, frozen_time):
        """Test converting context to model message."""
        mock_context = MagicMock(spec=Context)
        mock_context.content = "Previous conversation summary"
        mock_context.created_at = frozen_time - timedelta(minutes=10)

        result = context_to_model_message(mock_context, ts_reference=frozen_time)

        assert isinstance(result, pydantic_ai.messages.ModelResponse)
        assert result.kind == "response"
        assert len(result.parts) == 1

        text_part = result.parts[0]
        assert isinstance(text_part, pydantic_ai.messages.TextPart)
        assert text_part.part_kind == "text"

        # Parse the JSON content
        content_dict = json.loads(text_part.content)
        assert content_dict["timestamp"] == "600.0 seconds ago"
        assert "Summary of prior conversation" in content_dict["content"]
        assert "Previous conversation summary" in content_dict["content"]

    def test_context_to_model_message_default_reference(self):
        """Test context conversion with default reference time."""
        mock_context = MagicMock(spec=Context)
        mock_context.content = "Test content"
        mock_context.created_at = datetime.now(UTC) - timedelta(seconds=30)

        result = context_to_model_message(mock_context)

        assert isinstance(result, pydantic_ai.messages.ModelResponse)
        text_part = result.parts[0]
        content_dict = json.loads(text_part.content)

        # Should have timestamp with seconds ago
        assert "seconds ago" in content_dict["timestamp"]


class TestTelegramMessageToModelMessage:
    """Test the telegram_message_to_model_message function."""

    def test_user_message_text_only(self, frozen_time):
        """Test converting user text message to model message."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.text = "User input"
        mock_message.caption = None
        mock_message.message_id = 123
        mock_message.date = frozen_time - timedelta(seconds=10)

        result = telegram_message_to_model_message(
            message=mock_message, media=[], ts_reference=frozen_time, is_user=True
        )

        assert isinstance(result, pydantic_ai.messages.ModelRequest)
        assert result.kind == "request"
        assert len(result.parts) == 1

        user_part = result.parts[0]
        assert isinstance(user_part, pydantic_ai.messages.UserPromptPart)
        assert user_part.part_kind == "user-prompt"

        # Content should be JSON string
        content_dict = json.loads(user_part.content)
        assert content_dict["text"] == "User input"
        assert content_dict["message_id"] == "123"

    def test_user_message_with_image(self, frozen_time):
        """Test converting user message with image to model message."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.text = "Check this image"
        mock_message.caption = None
        mock_message.message_id = 456
        mock_message.date = frozen_time

        # Mock image media
        mock_image = MagicMock(spec=MediaFiles)
        mock_image.is_anthropic_supported = True
        mock_image.mime_type = "image/jpeg"
        mock_image.bytes_data = b"fake_image_data"

        result = telegram_message_to_model_message(
            message=mock_message, media=[mock_image], ts_reference=frozen_time, is_user=True
        )

        assert isinstance(result, pydantic_ai.messages.ModelRequest)
        user_part = result.parts[0]

        # Content should be a list with JSON and binary
        assert isinstance(user_part.content, list)
        assert len(user_part.content) == 2

        # First item is the message JSON
        assert isinstance(user_part.content[0], str)
        content_dict = json.loads(user_part.content[0])
        assert content_dict["text"] == "Check this image"

        # Second item is the binary content
        binary_content = user_part.content[1]
        assert isinstance(binary_content, pydantic_ai.BinaryContent)
        assert binary_content.data == b"fake_image_data"
        assert binary_content.media_type == "image/jpeg"

    def test_user_message_with_text_file(self, frozen_time):
        """Test converting user message with text file to model message."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.text = "Here's a text file"
        mock_message.caption = None
        mock_message.message_id = 789
        mock_message.date = frozen_time

        # Mock text file media
        mock_text = MagicMock(spec=MediaFiles)
        mock_text.is_anthropic_supported = True
        mock_text.mime_type = "text/plain"
        mock_text.bytes_data = b"Text file content"

        result = telegram_message_to_model_message(
            message=mock_message, media=[mock_text], ts_reference=frozen_time, is_user=True
        )

        user_part = result.parts[0]
        assert isinstance(user_part.content, list)
        assert len(user_part.content) == 2

        # Second item should be decoded text
        assert user_part.content[1] == "Text file content"

    def test_user_message_with_unsupported_media(self, frozen_time):
        """Test that unsupported media is filtered out."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.text = "Video message"
        mock_message.caption = None
        mock_message.message_id = 111
        mock_message.date = frozen_time

        # Mock unsupported video media
        mock_video = MagicMock(spec=MediaFiles)
        mock_video.is_anthropic_supported = False
        mock_video.mime_type = "video/mp4"

        result = telegram_message_to_model_message(
            message=mock_message, media=[mock_video], ts_reference=frozen_time, is_user=True
        )

        user_part = result.parts[0]
        # Content should only have the message JSON, no media
        assert isinstance(user_part.content, str)
        content_dict = json.loads(user_part.content)
        assert content_dict["text"] == "Video message"

    def test_bot_message(self, frozen_time):
        """Test converting bot message to model message."""
        mock_message = MagicMock(spec=telegram.Message)
        mock_message.text = "Bot response"
        mock_message.caption = None
        mock_message.message_id = 222
        mock_message.date = frozen_time

        result = telegram_message_to_model_message(
            message=mock_message, media=[], ts_reference=frozen_time, is_user=False
        )

        assert isinstance(result, pydantic_ai.messages.ModelResponse)
        assert result.kind == "response"
        assert len(result.parts) == 1

        text_part = result.parts[0]
        assert isinstance(text_part, pydantic_ai.messages.TextPart)
        assert text_part.part_kind == "text"

        content_dict = json.loads(text_part.content)
        assert content_dict["text"] == "Bot response"

    def test_user_reaction(self, frozen_time):
        """Test converting user reaction to model message."""
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 333
        mock_reaction.date = frozen_time

        mock_emoji_reaction = MagicMock()
        mock_emoji_reaction.type = telegram.constants.ReactionType.EMOJI
        mock_emoji_reaction.emoji = "❤️"
        mock_reaction.new_reaction = [mock_emoji_reaction]

        result = telegram_message_to_model_message(
            message=mock_reaction, media=[], ts_reference=frozen_time, is_user=True
        )

        assert isinstance(result, pydantic_ai.messages.ModelRequest)
        user_part = result.parts[0]
        content_dict = json.loads(user_part.content)
        assert content_dict["reaction"] == "❤️"
        assert content_dict["to_message_id"] == "333"

    def test_bot_reaction(self, frozen_time):
        """Test converting bot reaction to model message."""
        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.message_id = 444
        mock_reaction.date = frozen_time

        mock_emoji_reaction = MagicMock()
        mock_emoji_reaction.type = telegram.constants.ReactionType.EMOJI
        mock_emoji_reaction.emoji = "👍"
        mock_reaction.new_reaction = [mock_emoji_reaction]

        result = telegram_message_to_model_message(
            message=mock_reaction, media=[], ts_reference=frozen_time, is_user=False
        )

        assert isinstance(result, pydantic_ai.messages.ModelResponse)
        text_part = result.parts[0]
        content_dict = json.loads(text_part.content)
        assert content_dict["reaction"] == "👍"
