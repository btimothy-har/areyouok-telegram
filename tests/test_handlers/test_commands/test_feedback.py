"""Tests for handlers/commands/feedback.py."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote_plus

import pytest
import telegram
from telegram.constants import ReactionEmoji
from telegram.ext import ContextTypes

from areyouok_telegram.handlers.commands.feedback import (
    FEEDBACK_URL,
    on_feedback_command,
)


class TestOnFeedbackCommand:
    """Test the on_feedback_command handler."""

    @pytest.mark.asyncio
    async def test_feedback_command_with_active_session(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, mock_active_session, chat_factory
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

        # Use real Chat instance
        mock_chat = chat_factory(id_value=1)

        with (
            patch("uuid.uuid4", return_value=MagicMock(spec=uuid.UUID, __str__=lambda _: test_uuid)),
            patch(
                "areyouok_telegram.handlers.commands.feedback.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_sessions",
                new=AsyncMock(return_value=[mock_active_session]),
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
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

            # Command usage tracking happens via CommandUsage.save (already mocked)

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
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory
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

        # Use real Chat instance
        mock_chat = chat_factory(id_value=1)

        with (
            patch("uuid.uuid4", return_value=MagicMock(spec=uuid.UUID, __str__=lambda _: test_uuid)),
            patch(
                "areyouok_telegram.handlers.commands.feedback.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_sessions",
                new=AsyncMock(return_value=[]),  # No active session
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.commands.feedback.shorten_url", new=AsyncMock(return_value=test_short_url)
            ) as mock_shorten_url,
            patch("areyouok_telegram.handlers.commands.feedback.telegram_call", new=AsyncMock()) as mock_telegram_call,
            patch("areyouok_telegram.handlers.commands.feedback.package_version", return_value="1.0.0"),
            patch("areyouok_telegram.handlers.commands.feedback.ENV", "test"),
        ):
            await on_feedback_command(mock_update, mock_context)

            # Command usage tracking happens via CommandUsage.save (already mocked)

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


