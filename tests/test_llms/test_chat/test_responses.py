"""Tests for agent response types execution functionality."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from telegram.constants import ReactionEmoji

from areyouok_telegram.llms.chat.responses import DoNothingResponse
from areyouok_telegram.llms.chat.responses import ReactionResponse
from areyouok_telegram.llms.chat.responses import TextResponse


class TestTextResponse:
    """Test suite for TextResponse execution."""

    @pytest.mark.asyncio
    async def test_text_response_execute_simple_message(self, async_database_connection):
        """Test executing a simple text response without reply."""
        # Create mock context
        mock_context = AsyncMock()
        mock_sent_message = MagicMock(spec=telegram.Message)
        mock_context.bot.send_message.return_value = mock_sent_message

        # Create TextResponse
        response = TextResponse(
            reasoning="User needs encouragement",
            message_text="You're doing great! Keep going.",
            reply_to_message_id=None,
        )

        # Execute the response
        result = await response.execute(
            db_connection=async_database_connection, context=mock_context, chat_id="123456789"
        )

        # Verify the message was sent correctly
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=123456789, text="You're doing great! Keep going.", reply_parameters=None
        )

        assert result == mock_sent_message

    @pytest.mark.asyncio
    async def test_text_response_execute_with_reply(self, async_database_connection):
        """Test executing a text response with reply to specific message."""
        # Create mock context
        mock_context = AsyncMock()
        mock_sent_message = MagicMock(spec=telegram.Message)
        mock_context.bot.send_message.return_value = mock_sent_message

        # Create TextResponse with reply
        response = TextResponse(
            reasoning="Responding to user's specific question",
            message_text="That's a really good question. Let me think about that.",
            reply_to_message_id="456",
        )

        # Execute the response
        result = await response.execute(
            db_connection=async_database_connection, context=mock_context, chat_id="123456789"
        )

        # Verify the message was sent with reply parameters
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args

        assert call_args[1]["chat_id"] == 123456789
        assert call_args[1]["text"] == "That's a really good question. Let me think about that."
        assert call_args[1]["reply_parameters"] is not None
        assert call_args[1]["reply_parameters"].message_id == 456
        assert call_args[1]["reply_parameters"].allow_sending_without_reply is True

        assert result == mock_sent_message

    @pytest.mark.asyncio
    async def test_text_response_execute_handles_exception(self, async_database_connection):
        """Test that TextResponse handles exceptions during message sending."""
        # Create mock context that raises an exception
        mock_context = AsyncMock()
        mock_context.bot.send_message.side_effect = telegram.error.NetworkError("Network error")

        # Create TextResponse
        response = TextResponse(
            reasoning="User needs support", message_text="I'm here for you.", reply_to_message_id=None
        )

        # Execute should raise the exception
        with pytest.raises(telegram.error.NetworkError):
            await response.execute(db_connection=async_database_connection, context=mock_context, chat_id="123456789")

    @pytest.mark.asyncio
    async def test_text_response_retry_logic(self, async_database_connection):
        """Test that TextResponse retry logic works for transient errors."""
        # Create mock context that fails once then succeeds
        mock_context = AsyncMock()
        mock_sent_message = MagicMock(spec=telegram.Message)

        # First call fails, second succeeds
        mock_context.bot.send_message.side_effect = [telegram.error.TimedOut("Timeout"), mock_sent_message]

        # Create TextResponse
        response = TextResponse(
            reasoning="Testing retry logic", message_text="This should eventually work.", reply_to_message_id=None
        )

        # Execute the response
        result = await response.execute(
            db_connection=async_database_connection, context=mock_context, chat_id="123456789"
        )

        # Verify retry happened and eventually succeeded
        assert mock_context.bot.send_message.call_count == 2
        assert result == mock_sent_message


class TestReactionResponse:
    """Test suite for ReactionResponse execution."""

    @pytest.mark.asyncio
    async def test_reaction_response_execute_success(self, async_database_connection):
        """Test successful reaction response execution."""
        # Create mock context and message
        mock_context = AsyncMock()
        mock_context.bot.set_message_reaction.return_value = True

        mock_bot_user = MagicMock(spec=telegram.User)
        mock_bot_user.id = 999999999
        mock_context.bot.get_me.return_value = mock_bot_user

        # Create mock message from database
        mock_message = MagicMock()
        mock_message.chat = MagicMock(spec=telegram.Chat)

        # Create ReactionResponse
        response = ReactionResponse(
            reasoning="User message deserves a heart reaction", react_to_message_id="456", emoji=ReactionEmoji.RED_HEART
        )

        with patch(
            "areyouok_telegram.data.Messages.retrieve_message_by_id", return_value=(mock_message, None)
        ) as mock_retrieve:
            # Execute the response
            result = await response.execute(
                db_connection=async_database_connection, context=mock_context, chat_id="123456789"
            )

            # Verify database lookup
            mock_retrieve.assert_called_once_with(
                session=async_database_connection, message_id="456", chat_id="123456789"
            )

            # Verify reaction was set
            mock_context.bot.set_message_reaction.assert_called_once_with(
                chat_id=123456789, message_id=456, reaction=ReactionEmoji.RED_HEART
            )

            # Verify return value is MessageReactionUpdated
            assert isinstance(result, telegram.MessageReactionUpdated)
            assert result.message_id == 456
            assert len(result.new_reaction) == 1
            assert result.new_reaction[0].emoji == ReactionEmoji.RED_HEART

    @pytest.mark.asyncio
    async def test_reaction_response_execute_api_failure(self, async_database_connection):
        """Test reaction response when Telegram API fails."""
        # Create mock context that fails
        mock_context = AsyncMock()
        mock_context.bot.set_message_reaction.side_effect = telegram.error.BadRequest("Invalid message")

        # Create mock message from database
        mock_message = MagicMock()
        mock_message.chat = MagicMock(spec=telegram.Chat)

        # Create ReactionResponse
        response = ReactionResponse(
            reasoning="Want to react but will fail", react_to_message_id="456", emoji=ReactionEmoji.THUMBS_UP
        )

        with (
            patch("areyouok_telegram.data.Messages.retrieve_message_by_id", return_value=(mock_message, None)),
            pytest.raises(telegram.error.BadRequest),
        ):
            await response.execute(db_connection=async_database_connection, context=mock_context, chat_id="123456789")

    @pytest.mark.asyncio
    async def test_reaction_response_execute_set_reaction_returns_false(self, async_database_connection):
        """Test reaction response when set_message_reaction returns False."""
        # Create mock context that returns False
        mock_context = AsyncMock()
        mock_context.bot.set_message_reaction.return_value = False

        # Create mock message from database
        mock_message = MagicMock()
        mock_message.chat = MagicMock(spec=telegram.Chat)

        # Create ReactionResponse
        response = ReactionResponse(
            reasoning="Reaction that returns False", react_to_message_id="456", emoji=ReactionEmoji.THUMBS_DOWN
        )

        with patch("areyouok_telegram.data.Messages.retrieve_message_by_id", return_value=(mock_message, None)):
            result = await response.execute(
                db_connection=async_database_connection, context=mock_context, chat_id="123456789"
            )

            # When set_message_reaction returns False, result should be None
            assert result is None

    @pytest.mark.asyncio
    async def test_reaction_response_retry_logic(self, async_database_connection):
        """Test that ReactionResponse retry logic works for transient errors."""
        # Create mock context that fails once then succeeds
        mock_context = AsyncMock()
        mock_context.bot.set_message_reaction.side_effect = [telegram.error.NetworkError("Network error"), True]

        mock_bot_user = MagicMock(spec=telegram.User)
        mock_context.bot.get_me.return_value = mock_bot_user

        # Create mock message from database
        mock_message = MagicMock()
        mock_message.chat = MagicMock(spec=telegram.Chat)

        # Create ReactionResponse
        response = ReactionResponse(
            reasoning="Testing retry logic", react_to_message_id="456", emoji=ReactionEmoji.FIRE
        )

        with patch("areyouok_telegram.data.Messages.retrieve_message_by_id", return_value=(mock_message, None)):
            result = await response.execute(
                db_connection=async_database_connection, context=mock_context, chat_id="123456789"
            )

            # Verify retry happened and eventually succeeded
            assert mock_context.bot.set_message_reaction.call_count == 2
            assert isinstance(result, telegram.MessageReactionUpdated)


class TestDoNothingResponse:
    """Test suite for DoNothingResponse execution."""

    @pytest.mark.asyncio
    async def test_do_nothing_response_execute(self, async_database_connection):
        """Test DoNothingResponse execution does nothing."""
        # Create mock context
        mock_context = AsyncMock()

        # Create DoNothingResponse
        response = DoNothingResponse(reasoning="User is just making small talk, no response needed")

        # Execute the response
        result = await response.execute(
            db_connection=async_database_connection, context=mock_context, chat_id="123456789"
        )

        # Verify no actions were taken
        assert result is None

        # Verify no bot methods were called
        assert not mock_context.bot.method_calls

    def test_do_nothing_response_type_property(self):
        """Test DoNothingResponse response_type property."""
        response = DoNothingResponse(reasoning="No action needed")

        assert response.response_type == "DoNothingResponse"


class TestBaseAgentResponse:
    """Test suite for BaseAgentResponse functionality."""

    def test_response_type_property(self):
        """Test that response_type property returns correct class name."""
        text_response = TextResponse(reasoning="Test reasoning", message_text="Test message")

        reaction_response = ReactionResponse(
            reasoning="Test reasoning", react_to_message_id="123", emoji=ReactionEmoji.RED_HEART
        )

        do_nothing_response = DoNothingResponse(reasoning="Test reasoning")

        assert text_response.response_type == "TextResponse"
        assert reaction_response.response_type == "ReactionResponse"
        assert do_nothing_response.response_type == "DoNothingResponse"
