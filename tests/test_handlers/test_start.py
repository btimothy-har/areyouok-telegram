"""Tests for handlers/start.py."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch
from unittest import mock

import pytest
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import SYSTEM_USER_ID
from areyouok_telegram.data import GuidedSessionType
from areyouok_telegram.handlers.start import on_start_command


class TestOnStartCommand:
    """Test the on_start_command handler."""

    @pytest.mark.asyncio
    async def test_on_start_command_with_incomplete_onboarding(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
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

        # Create mock session and onboarding session
        mock_session = MagicMock()
        mock_session.session_key = "test_session_key"
        mock_session.last_bot_activity = "2024-01-01T10:00:00Z"  # Has previous activity, no greeting

        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_completed = False

        with (
            patch(
                "areyouok_telegram.handlers.start.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session)
            ) as mock_get_session,
            patch(
                "areyouok_telegram.handlers.start.data_operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session)
            ) as mock_get_guided_session,
            patch(
                "areyouok_telegram.handlers.start.data_operations.new_session_event",
                new=AsyncMock()
            ) as mock_new_session_event,
        ):
            await on_start_command(mock_update, mock_context)

            # Verify operations with data_operations module
            mock_get_session.assert_called_once_with(
                chat_id=str(mock_telegram_chat.id),
                timestamp=mock_telegram_message.date,
            )
            mock_get_guided_session.assert_called_once_with(
                chat_id=str(mock_telegram_chat.id),
                session=mock_session,
                stype=GuidedSessionType.ONBOARDING
            )
            mock_new_session_event.assert_called_once_with(
                session=mock_session,
                message=mock_telegram_message,
                user_id=str(mock_telegram_user.id),
                is_user=True,
            )

            # No message should be sent to user since no onboarding greeting condition is met
            mock_context.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_start_command_with_completed_onboarding(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
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

        # Create mock session and completed onboarding session
        mock_session = MagicMock()
        mock_session.session_key = "test_session_key"

        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_completed = True

        with (
            patch(
                "areyouok_telegram.handlers.start.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session)
            ) as mock_get_session,
            patch(
                "areyouok_telegram.handlers.start.data_operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session)
            ) as mock_get_guided_session,
            patch(
                "areyouok_telegram.handlers.start.data_operations.new_session_event",
                new=AsyncMock()
            ) as mock_new_session_event,
            patch(
                "areyouok_telegram.handlers.start.MD2_ONBOARDING_COMPLETE_MESSAGE", "Onboarding already completed!"
            ),
        ):
            await on_start_command(mock_update, mock_context)

            # Verify session operations
            mock_get_session.assert_called_once_with(
                chat_id=str(mock_telegram_chat.id),
                timestamp=mock_telegram_message.date,
            )
            mock_get_guided_session.assert_called_once_with(
                chat_id=str(mock_telegram_chat.id),
                session=mock_session,
                stype=GuidedSessionType.ONBOARDING
            )

            # Should not save session event since early return
            mock_new_session_event.assert_not_called()

            # Should send completion message to user
            mock_context.bot.send_message.assert_called_once_with(
                chat_id=mock_telegram_chat.id,
                text="Onboarding already completed!",
                parse_mode="MarkdownV2",
            )

    @pytest.mark.asyncio
    async def test_on_start_command_sends_greeting_message_for_new_user(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
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
        mock_bot_message = MagicMock(spec=telegram.Message)
        mock_context.bot.send_message.return_value = mock_bot_message

        # Create mock session and onboarding session
        mock_session = MagicMock()
        mock_session.session_key = "test_session_key"
        mock_session.last_bot_activity = None  # Key condition for sending greeting

        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_completed = False

        with (
            patch(
                "areyouok_telegram.handlers.start.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session)
            ) as mock_get_session,
            patch(
                "areyouok_telegram.handlers.start.data_operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session)
            ) as mock_get_guided_session,
            patch(
                "areyouok_telegram.handlers.start.data_operations.new_session_event",
                new=AsyncMock()
            ) as mock_new_session_event,
            patch("areyouok_telegram.handlers.start.MD2_ONBOARDING_START_MESSAGE", "Hello there! Please wait..."),
        ):
            await on_start_command(mock_update, mock_context)

            # Verify session operations
            mock_get_session.assert_called_once_with(
                chat_id=str(mock_telegram_chat.id),
                timestamp=mock_telegram_message.date,
            )
            mock_get_guided_session.assert_called_once_with(
                chat_id=str(mock_telegram_chat.id),
                session=mock_session,
                stype=GuidedSessionType.ONBOARDING
            )

            # Verify session events were logged
            assert mock_new_session_event.call_count == 2

            # First call: user message event
            user_event_call = mock_new_session_event.call_args_list[0]
            assert user_event_call[1]["session"] == mock_session
            assert user_event_call[1]["message"] == mock_telegram_message
            assert user_event_call[1]["user_id"] == str(mock_telegram_user.id)
            assert user_event_call[1]["is_user"] == True

            # Second call: bot greeting message event
            bot_event_call = mock_new_session_event.call_args_list[1]
            assert bot_event_call[1]["session"] == mock_session
            assert bot_event_call[1]["message"] == mock_bot_message
            assert bot_event_call[1]["user_id"] == SYSTEM_USER_ID
            assert bot_event_call[1]["is_user"] == False

            # Verify greeting message was sent
            mock_context.bot.send_message.assert_called_once_with(
                chat_id=mock_telegram_chat.id,
                text="Hello there! Please wait...",
                parse_mode="MarkdownV2",
            )