"""Tests for handlers/start.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data.models import GuidedSessionType
from areyouok_telegram.handlers.commands.start import on_start_command


class TestOnStartCommand:
    """Test the on_start_command handler."""

    @pytest.mark.asyncio
    async def test_on_start_command_with_incomplete_onboarding(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, user_factory, session_factory
    ):
        """Test on_start_command when onboarding is not completed."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_chat = mock_telegram_chat
        mock_update.effective_user = mock_telegram_user
        mock_update.message = mock_telegram_message

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Use real Pydantic instances
        mock_chat = chat_factory(id_value=1)
        mock_user = user_factory(id_value=100)
        mock_session = session_factory(chat=mock_chat, id_value=123)
        # Add last_bot_activity to prevent greeting
        mock_session.last_bot_activity = "2024-01-01T10:00:00Z"

        # Create mock onboarding session
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_completed = False
        mock_onboarding_session.is_incomplete = True

        with (
            patch(
                "areyouok_telegram.handlers.commands.start.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.handlers.commands.start.User.get_by_id",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ) as mock_get_session,
            patch(
                "areyouok_telegram.data.models.GuidedSession.get_by_chat",
                new=AsyncMock(return_value=[mock_onboarding_session]),
            ) as mock_get_guided_session,
            patch("areyouok_telegram.data.models.GuidedSession.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.data.models.Message.from_telegram",
                return_value=MagicMock(save=AsyncMock()),
            ),
            patch("areyouok_telegram.data.models.Session.new_message", new=AsyncMock()),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
        ):
            await on_start_command(mock_update, mock_context)

            # Verify session was created with correct params
            mock_get_session.assert_called_once_with(
                chat=mock_chat,
                session_start=mock_telegram_message.date,
            )

            # Verify guided session lookup
            mock_get_guided_session.assert_called_once_with(
                chat=mock_chat,
                session_type=GuidedSessionType.ONBOARDING.value,
            )

            # No message should be sent to user since bot has previous activity
            mock_context.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_start_command_with_completed_onboarding(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, user_factory, session_factory
    ):
        """Test on_start_command when onboarding is already completed."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_chat = mock_telegram_chat
        mock_update.effective_user = mock_telegram_user
        mock_update.message = mock_telegram_message

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Use real Pydantic instances
        mock_chat = chat_factory(id_value=1)
        mock_user = user_factory(id_value=100)
        mock_session = session_factory(chat=mock_chat, id_value=123)

        # Create completed onboarding session
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_completed = True

        with (
            patch(
                "areyouok_telegram.handlers.commands.start.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.handlers.commands.start.User.get_by_id",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch(
                "areyouok_telegram.data.models.GuidedSession.get_by_chat",
                new=AsyncMock(return_value=[mock_onboarding_session]),
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.commands.start.MD2_ONBOARDING_COMPLETE_MESSAGE",
                "Onboarding already completed!",
            ),
        ):
            await on_start_command(mock_update, mock_context)

            # Should send completion message to user
            mock_context.bot.send_message.assert_called_once_with(
                chat_id=mock_telegram_chat.id,
                text="Onboarding already completed!",
                parse_mode="MarkdownV2",
            )

    @pytest.mark.asyncio
    async def test_on_start_command_sends_greeting_message_for_new_user(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, user_factory, session_factory
    ):
        """Test on_start_command sends greeting message when user has no prior bot activity."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_chat = mock_telegram_chat
        mock_update.effective_user = mock_telegram_user
        mock_update.message = mock_telegram_message

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Use real Pydantic instances
        mock_chat = chat_factory(id_value=1)
        mock_user = user_factory(id_value=100)
        mock_session = session_factory(chat=mock_chat, id_value=123)
        # Key condition: no last_bot_activity

        # Create incomplete onboarding session
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_completed = False
        mock_onboarding_session.is_incomplete = True

        with (
            patch(
                "areyouok_telegram.handlers.commands.start.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.handlers.commands.start.User.get_by_id",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch(
                "areyouok_telegram.data.models.GuidedSession.get_by_chat",
                new=AsyncMock(return_value=[mock_onboarding_session]),
            ),
            patch("areyouok_telegram.data.models.GuidedSession.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.data.models.Message.from_telegram",
                return_value=MagicMock(save=AsyncMock()),
            ),
            patch("areyouok_telegram.data.models.Session.new_message", new=AsyncMock()),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.commands.start.MD2_ONBOARDING_START_MESSAGE",
                "Hello there! Please wait...",
            ),
        ):
            await on_start_command(mock_update, mock_context)

            # Verify greeting message was sent
            mock_context.bot.send_message.assert_called_once_with(
                chat_id=mock_telegram_chat.id,
                text="Hello there! Please wait...",
                parse_mode="MarkdownV2",
            )
