"""Tests for handlers/commands/feedback.py."""

import uuid
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch
from urllib.parse import quote_plus

import pytest
import telegram
from telegram.constants import ReactionEmoji
from telegram.ext import ContextTypes

from areyouok_telegram.handlers.commands.feedback import FEEDBACK_CACHE
from areyouok_telegram.handlers.commands.feedback import FEEDBACK_URL
from areyouok_telegram.handlers.commands.feedback import generate_feedback_context
from areyouok_telegram.handlers.commands.feedback import on_feedback_command


class TestOnFeedbackCommand:
    """Test the on_feedback_command handler."""

    @pytest.mark.asyncio
    async def test_feedback_command_with_active_session(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, mock_active_session
    ):
        """Test feedback command with active session generates proper URL and UI."""
        # Setup
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_chat = mock_telegram_chat
        mock_update.effective_user = mock_telegram_user
        mock_update.message = mock_telegram_message

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()
        mock_context.bot.id = 123456

        test_uuid = "test-uuid-123"
        test_feedback_context = "User discussed emotional support needs with bot."
        test_short_url = "https://tinyurl.com/test123"

        with (
            patch("uuid.uuid4", return_value=MagicMock(spec=uuid.UUID, __str__=lambda _: test_uuid)),
            patch(
                "areyouok_telegram.handlers.commands.feedback.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ),
            patch(
                "areyouok_telegram.handlers.commands.feedback.data_operations.track_command_usage", new=AsyncMock()
            ) as mock_track,
            patch(
                "areyouok_telegram.handlers.commands.feedback.generate_feedback_context",
                new=AsyncMock(return_value=test_feedback_context),
            ) as mock_generate_context,
            patch(
                "areyouok_telegram.handlers.commands.feedback.shorten_url", new=AsyncMock(return_value=test_short_url)
            ) as mock_shorten_url,
            patch("areyouok_telegram.handlers.commands.feedback.telegram_call", new=AsyncMock()) as mock_telegram_call,
            patch("areyouok_telegram.handlers.commands.feedback.package_version", return_value="1.0.0"),
            patch("areyouok_telegram.handlers.commands.feedback.ENV", "test"),
        ):
            await on_feedback_command(mock_update, mock_context)

            # Verify session retrieval
            assert mock_track.call_count == 1
            mock_track.assert_called_with(
                command="feedback",
                chat_id=str(mock_telegram_chat.id),
                session_id=mock_active_session.session_id,
            )

            # Verify feedback context generation
            mock_generate_context.assert_called_once_with(
                bot_id="123456",
                session=mock_active_session,
            )

            # Verify bot reactions and typing
            assert mock_telegram_call.call_count == 3

            # Check message reaction call
            reaction_call = mock_telegram_call.call_args_list[0]
            assert reaction_call[0][0] == mock_context.bot.set_message_reaction
            assert reaction_call[1]["chat_id"] == mock_telegram_chat.id
            assert reaction_call[1]["message_id"] == mock_telegram_message.message_id
            assert reaction_call[1]["reaction"] in [
                ReactionEmoji.THUMBS_UP,
                ReactionEmoji.EYES,
                ReactionEmoji.THINKING_FACE,
                ReactionEmoji.SALUTING_FACE,
            ]

            # Check typing action call
            typing_call = mock_telegram_call.call_args_list[1]
            assert typing_call[0][0] == mock_context.bot.send_chat_action
            assert typing_call[1]["chat_id"] == mock_telegram_chat.id
            assert typing_call[1]["action"] == telegram.constants.ChatAction.TYPING

            # Check message send call
            send_call = mock_telegram_call.call_args_list[2]
            assert send_call[0][0] == mock_context.bot.send_message
            assert send_call[1]["chat_id"] == mock_telegram_chat.id
            assert "parse_mode" in send_call[1]
            assert "reply_markup" in send_call[1]

            # Verify URL shortening
            expected_long_url = FEEDBACK_URL.format(
                uuid=quote_plus(test_uuid),
                session_id=quote_plus(mock_active_session.session_id),
                context=quote_plus(test_feedback_context),
                env=quote_plus("test"),
                version=quote_plus("1.0.0"),
            )
            mock_shorten_url.assert_called_once_with(expected_long_url)

    @pytest.mark.asyncio
    async def test_feedback_command_without_active_session(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test feedback command without active session uses fallback values."""
        # Setup
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_chat = mock_telegram_chat
        mock_update.effective_user = mock_telegram_user
        mock_update.message = mock_telegram_message

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()
        mock_context.bot.id = 123456

        test_uuid = "test-uuid-456"
        test_short_url = "https://tinyurl.com/test456"

        with (
            patch("uuid.uuid4", return_value=MagicMock(spec=uuid.UUID, __str__=lambda _: test_uuid)),
            patch(
                "areyouok_telegram.handlers.commands.feedback.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "areyouok_telegram.handlers.commands.feedback.data_operations.track_command_usage", new=AsyncMock()
            ) as mock_track,
            patch(
                "areyouok_telegram.handlers.commands.feedback.shorten_url", new=AsyncMock(return_value=test_short_url)
            ) as mock_shorten_url,
            patch("areyouok_telegram.handlers.commands.feedback.telegram_call", new=AsyncMock()) as mock_telegram_call,
            patch("areyouok_telegram.handlers.commands.feedback.package_version", return_value="1.0.0"),
            patch("areyouok_telegram.handlers.commands.feedback.ENV", "test"),
        ):
            await on_feedback_command(mock_update, mock_context)

            # Verify command usage tracking with None session_id
            mock_track.assert_called_once_with(
                command="feedback",
                chat_id=str(mock_telegram_chat.id),
                session_id=None,
            )

            # Verify URL shortening with fallback values
            expected_long_url = FEEDBACK_URL.format(
                uuid=quote_plus(test_uuid),
                session_id=quote_plus("no_active_session"),
                context=quote_plus("No active session found."),
                env=quote_plus("test"),
                version=quote_plus("1.0.0"),
            )
            mock_shorten_url.assert_called_once_with(expected_long_url)

            # Verify only one telegram call (send_message, no reactions/typing for no session)
            assert mock_telegram_call.call_count == 1

    @pytest.mark.asyncio
    async def test_feedback_url_format(self):
        """Test that feedback URL contains all expected parameters with URL encoding."""
        test_values = {
            "uuid": quote_plus("test-uuid-789"),
            "session_id": quote_plus("session-123"),
            "context": quote_plus("Test context"),
            "env": quote_plus("test"),
            "version": quote_plus("1.2.3"),
        }

        formatted_url = FEEDBACK_URL.format(**test_values)

        # Check that all parameters are included in URL with proper URL encoding
        assert "entry.265305704=test-uuid-789" in formatted_url
        assert "entry.1140367297=session-123" in formatted_url
        assert "entry.604567897=Test+context" in formatted_url  # Spaces encoded as +
        assert "entry.4225678=test" in formatted_url
        assert "entry.191939218=1.2.3" in formatted_url


class TestGenerateFeedbackContext:
    """Test the generate_feedback_context function."""

    @pytest.mark.asyncio
    async def test_generate_context_with_sufficient_messages(self, frozen_time, mock_active_session, mock_db_session):
        """Test context generation with sufficient messages."""
        # Setup mock messages
        mock_messages = []
        for i in range(15):  # More than 10 messages
            msg = MagicMock()
            msg.message_type = "Message" if i % 2 == 0 else "MessageReactionUpdated"
            msg.message_id = f"msg_{i}"
            msg.decrypt = MagicMock()
            mock_messages.append(msg)

        mock_chat = MagicMock()
        mock_chat.retrieve_key = MagicMock(return_value=b"test_key")

        mock_context_items = [MagicMock() for _ in range(3)]
        for ctx in mock_context_items:
            ctx.type = "user_preference"  # Not SESSION type
            ctx.decrypt_content = MagicMock()

        mock_agent_payload = MagicMock()
        mock_agent_payload.output = "Generated feedback context summary"

        with (
            patch("areyouok_telegram.handlers.commands.feedback.async_database") as mock_db,
            patch("areyouok_telegram.handlers.commands.feedback.Chats") as mock_chats,
            patch("areyouok_telegram.handlers.commands.feedback.MediaFiles") as mock_media,
            patch("areyouok_telegram.handlers.commands.feedback.Context") as mock_context_model,
            patch("areyouok_telegram.handlers.commands.feedback.ChatEvent") as mock_chat_event,
            patch(
                "areyouok_telegram.handlers.commands.feedback.run_agent_with_tracking",
                new=AsyncMock(return_value=mock_agent_payload),
            ) as mock_run_agent,
        ):
            mock_db.return_value.__aenter__.return_value = mock_db_session
            mock_chats.get_by_id = AsyncMock(return_value=mock_chat)
            mock_active_session.get_messages = AsyncMock(return_value=mock_messages)
            mock_active_session.session_id = "test_session_123"
            mock_active_session.chat_id = "test_chat_456"

            mock_media.get_by_message_id = AsyncMock(return_value=[])
            mock_context_model.get_by_session_id = AsyncMock(return_value=mock_context_items)

            # Create proper mock events with timestamps for sorting
            mock_msg_event = MagicMock()
            mock_msg_event.timestamp = frozen_time
            mock_ctx_event = MagicMock()
            mock_ctx_event.timestamp = frozen_time

            mock_chat_event.from_message = MagicMock(return_value=mock_msg_event)
            mock_chat_event.from_context = MagicMock(return_value=mock_ctx_event)

            # Clear cache before test
            FEEDBACK_CACHE.clear()

            result = await generate_feedback_context("bot_123", mock_active_session)

            assert result == "Generated feedback context summary"

            # Verify database calls
            mock_chats.get_by_id.assert_called_once_with(mock_db_session, chat_id="test_chat_456")
            mock_active_session.get_messages.assert_called_once_with(mock_db_session)

            # Verify decryption calls
            for msg in mock_messages:
                msg.decrypt.assert_called_once_with(b"test_key")

            # Verify agent was called
            mock_run_agent.assert_called_once()

            # Verify result is cached
            assert "test_chat_456" in FEEDBACK_CACHE

    @pytest.mark.asyncio
    async def test_generate_context_with_insufficient_messages(self, mock_active_session, mock_db_session):
        """Test context generation with insufficient messages returns early."""
        # Setup with only 5 messages (less than 10)
        mock_messages = [MagicMock() for _ in range(5)]

        mock_chat = MagicMock()
        mock_chat.retrieve_key = MagicMock(return_value=b"test_key")

        with (
            patch("areyouok_telegram.handlers.commands.feedback.async_database") as mock_db,
            patch("areyouok_telegram.handlers.commands.feedback.Chats") as mock_chats,
        ):
            mock_db.return_value.__aenter__.return_value = mock_db_session
            mock_chats.get_by_id = AsyncMock(return_value=mock_chat)
            mock_active_session.get_messages = AsyncMock(return_value=mock_messages)
            mock_active_session.chat_id = "test_chat_789"

            # Clear cache before test
            FEEDBACK_CACHE.clear()

            result = await generate_feedback_context("bot_123", mock_active_session)

            assert result == "Less than 10 messages in the session. Not enough context for feedback context."

    @pytest.mark.asyncio
    async def test_generate_context_uses_cache(self, mock_active_session):
        """Test that cached context is returned when available and fresh."""
        cache_key = "test_chat_cache"
        cached_output = "Cached feedback context"
        cache_timestamp = datetime.now(UTC)

        # Setup cache
        FEEDBACK_CACHE[cache_key] = (cached_output, cache_timestamp)
        mock_active_session.chat_id = cache_key

        with patch("areyouok_telegram.handlers.commands.feedback.datetime") as mock_datetime:
            # Mock current time to be within cache TTL (< 300 seconds)
            mock_datetime.now.return_value = cache_timestamp + timedelta(seconds=200)
            mock_datetime.UTC = UTC

            result = await generate_feedback_context("bot_123", mock_active_session)

            assert result == cached_output

    @pytest.mark.asyncio
    async def test_generate_context_cache_expired(self, frozen_time, mock_active_session, mock_db_session):
        """Test that expired cache is ignored and new context is generated."""
        cache_key = "test_chat_expired"
        cached_output = "Old cached context"
        cache_timestamp = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)  # Old timestamp

        # Setup expired cache
        FEEDBACK_CACHE[cache_key] = (cached_output, cache_timestamp)
        mock_active_session.chat_id = cache_key
        mock_active_session.session_id = "test_session"

        # Setup fresh context generation
        mock_messages = [MagicMock() for _ in range(12)]
        for msg in mock_messages:
            msg.message_type = "Message"
            msg.decrypt = MagicMock()

        mock_chat = MagicMock()
        mock_chat.retrieve_key = MagicMock(return_value=b"test_key")

        mock_agent_payload = MagicMock()
        mock_agent_payload.output = "Fresh feedback context"

        with (
            patch("areyouok_telegram.handlers.commands.feedback.datetime") as mock_datetime,
            patch("areyouok_telegram.handlers.commands.feedback.async_database") as mock_db,
            patch("areyouok_telegram.handlers.commands.feedback.Chats") as mock_chats,
            patch("areyouok_telegram.handlers.commands.feedback.MediaFiles") as mock_media,
            patch("areyouok_telegram.handlers.commands.feedback.Context") as mock_context_model,
            patch("areyouok_telegram.handlers.commands.feedback.ChatEvent") as mock_chat_event,
            patch(
                "areyouok_telegram.handlers.commands.feedback.run_agent_with_tracking",
                new=AsyncMock(return_value=mock_agent_payload),
            ) as mock_run_agent,
        ):
            # Mock current time to be beyond cache TTL (> 300 seconds)
            current_time = cache_timestamp + timedelta(seconds=400)
            mock_datetime.now.return_value = current_time
            mock_datetime.UTC = UTC

            mock_db.return_value.__aenter__.return_value = mock_db_session
            mock_chats.get_by_id = AsyncMock(return_value=mock_chat)
            mock_active_session.get_messages = AsyncMock(return_value=mock_messages)
            mock_media.get_by_message_id = AsyncMock(return_value=[])
            mock_context_model.get_by_session_id = AsyncMock(return_value=[])

            # Create proper mock events with timestamps for sorting
            mock_msg_event = MagicMock()
            mock_msg_event.timestamp = frozen_time

            mock_chat_event.from_message = MagicMock(return_value=mock_msg_event)

            result = await generate_feedback_context("bot_123", mock_active_session)

            assert result == "Fresh feedback context"
            mock_run_agent.assert_called_once()
