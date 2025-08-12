"""Test module for LLM utilities."""

import json
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import logfire
import pydantic_ai
import pytest
import telegram

from areyouok_telegram.data import Context
from areyouok_telegram.llms.utils import context_to_model_message
from areyouok_telegram.llms.utils import message_to_dict
from areyouok_telegram.llms.utils import message_to_model_message
from areyouok_telegram.llms.utils import run_agent_with_tracking


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
        mock_result = MagicMock()
        mock_result.usage.return_value = {"tokens": 100}
        mock_agent.run.return_value = mock_result

        # Mock database and tracking
        with patch("areyouok_telegram.llms.utils.async_database") as mock_db, patch(
            "areyouok_telegram.llms.utils.LLMUsage.track_pydantic_usage"
        ) as mock_track:
            mock_db_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_db_conn

            result = await run_agent_with_tracking(
                agent=mock_agent, chat_id="123", session_id="session123", run_kwargs={"message_history": []}
            )

            # Verify agent was called
            mock_agent.run.assert_called_once_with(message_history=[])

            # Verify tracking was called
            mock_track.assert_called_once_with(
                db_conn=mock_db_conn,
                chat_id="123",
                session_id="session123",
                agent=mock_agent,
                data={"tokens": 100},
            )

            # Verify result was returned
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_run_agent_with_tracking_missing_kwargs(self):
        """Test error when neither user_prompt nor message_history is provided."""
        mock_agent = MagicMock(spec=pydantic_ai.Agent)

        with pytest.raises(ValueError, match="Either 'user_prompt' or 'message_history' must be provided"):
            await run_agent_with_tracking(
                agent=mock_agent, chat_id="123", session_id="session123", run_kwargs={}
            )

    @pytest.mark.asyncio
    async def test_run_agent_with_tracking_logs_error(self):
        """Test that tracking errors are logged but don't fail the function."""
        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_agent.run = AsyncMock()

        # Mock result
        mock_result = MagicMock()
        mock_result.usage.return_value = {"tokens": 100}
        mock_agent.run.return_value = mock_result

        # Mock database to raise an error
        with patch("areyouok_telegram.llms.utils.async_database") as mock_db, patch.object(
            logfire, "exception"
        ) as mock_log:
            mock_db.side_effect = Exception("Database error")

            result = await run_agent_with_tracking(
                agent=mock_agent, chat_id="123", session_id="session123", run_kwargs={"user_prompt": "test"}
            )

            # Verify error was logged
            mock_log.assert_called_once()
            log_call = mock_log.call_args
            assert "Failed to log LLM usage" in log_call[0][0]
            assert log_call.kwargs["agent"] == "test_agent"
            assert log_call.kwargs["chat_id"] == "123"
            assert log_call.kwargs["session_id"] == "session123"

        # Verify result was still returned
        assert result == mock_result


class TestMessageToDict:
    """Test the message_to_dict function."""

    def test_message_to_dict_with_text(self, frozen_time):
        """Test converting a text message to dict."""
        # Mock Messages SQLAlchemy object
        mock_messages = MagicMock()
        mock_messages.message_type = "Message"
        mock_messages.message_id = "123"
        mock_messages.reasoning = None

        # Mock telegram object
        mock_telegram_obj = MagicMock(spec=telegram.Message)
        mock_telegram_obj.text = "Hello world"
        mock_telegram_obj.caption = None
        mock_telegram_obj.message_id = 123
        mock_telegram_obj.date = frozen_time - timedelta(seconds=30)
        mock_messages.telegram_object = mock_telegram_obj

        result = message_to_dict(mock_messages, ts_reference=frozen_time)

        assert result == {"text": "Hello world", "message_id": "123", "timestamp": "30 seconds ago"}

    def test_message_to_dict_with_caption(self, frozen_time):
        """Test converting a message with caption to dict."""
        mock_messages = MagicMock()
        mock_messages.message_type = "Message"
        mock_messages.message_id = "456"
        mock_messages.reasoning = None

        mock_telegram_obj = MagicMock(spec=telegram.Message)
        mock_telegram_obj.text = None
        mock_telegram_obj.caption = "Photo caption"
        mock_telegram_obj.message_id = 456
        mock_telegram_obj.date = frozen_time - timedelta(minutes=5)
        mock_messages.telegram_object = mock_telegram_obj

        result = message_to_dict(mock_messages, ts_reference=frozen_time)

        assert result == {"text": "Photo caption", "message_id": "456", "timestamp": "300 seconds ago"}

    def test_message_to_dict_with_reasoning(self, frozen_time):
        """Test converting a message with reasoning to dict."""
        mock_messages = MagicMock()
        mock_messages.message_type = "Message"
        mock_messages.message_id = "789"
        mock_messages.reasoning = "This is AI reasoning"

        mock_telegram_obj = MagicMock(spec=telegram.Message)
        mock_telegram_obj.text = "Bot response"
        mock_telegram_obj.caption = None
        mock_telegram_obj.message_id = 789
        mock_telegram_obj.date = frozen_time
        mock_messages.telegram_object = mock_telegram_obj

        result = message_to_dict(mock_messages, ts_reference=frozen_time)

        assert result == {
            "text": "Bot response",
            "message_id": "789",
            "timestamp": "0 seconds ago",
            "reasoning": "This is AI reasoning"
        }


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


class TestMessageToModelMessage:
    """Test the message_to_model_message function."""

    def test_user_message_text_only(self, frozen_time):
        """Test converting user text message to model message."""
        # Mock Messages SQLAlchemy object
        mock_messages = MagicMock()
        mock_messages.message_type = "Message"
        mock_messages.message_id = "123"
        mock_messages.reasoning = None

        # Mock telegram object
        mock_telegram_obj = MagicMock(spec=telegram.Message)
        mock_telegram_obj.text = "User input"
        mock_telegram_obj.caption = None
        mock_telegram_obj.message_id = 123
        mock_telegram_obj.date = frozen_time - timedelta(seconds=10)
        mock_messages.telegram_object = mock_telegram_obj

        result = message_to_model_message(
            message=mock_messages, media=[], ts_reference=frozen_time, is_user=True
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

    def test_bot_message_with_reasoning(self, frozen_time):
        """Test converting bot message with reasoning to model message."""
        # Mock Messages SQLAlchemy object with reasoning
        mock_messages = MagicMock()
        mock_messages.message_type = "Message"
        mock_messages.message_id = "456"
        mock_messages.reasoning = "I responded this way because..."

        # Mock telegram object
        mock_telegram_obj = MagicMock(spec=telegram.Message)
        mock_telegram_obj.text = "Bot response text"
        mock_telegram_obj.caption = None
        mock_telegram_obj.message_id = 456
        mock_telegram_obj.date = frozen_time
        mock_messages.telegram_object = mock_telegram_obj

        result = message_to_model_message(
            message=mock_messages, media=[], ts_reference=frozen_time, is_user=False
        )

        assert isinstance(result, pydantic_ai.messages.ModelResponse)
        assert result.kind == "response"
        assert len(result.parts) == 1

        text_part = result.parts[0]
        assert isinstance(text_part, pydantic_ai.messages.TextPart)
        assert text_part.part_kind == "text"

        # Content should include reasoning
        content_dict = json.loads(text_part.content)
        assert content_dict["text"] == "Bot response text"
        assert content_dict["message_id"] == "456"
        assert content_dict["reasoning"] == "I responded this way because..."
