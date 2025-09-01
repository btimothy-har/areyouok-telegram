"""Tests for handlers/commands.py."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.handlers.commands import on_end_command
from areyouok_telegram.handlers.commands import on_start_command


class TestOnStartCommand:
    """Test the on_start_command handler."""

    @pytest.mark.asyncio
    async def test_on_start_command_no_existing_session_no_onboarding(
        self, mock_db_session, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test on_start_command when no session exists and no onboarding history."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_chat = mock_telegram_chat
        mock_update.effective_user = mock_telegram_user
        mock_update.message = mock_telegram_message

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Create mock objects
        mock_chat_obj = MagicMock()
        mock_chat_obj.retrieve_key.return_value = "test_encryption_key"

        mock_session = MagicMock()
        mock_session.session_key = "test_session_key"

        with (
            patch(
                "areyouok_telegram.handlers.commands.Chats.get_by_id", new=AsyncMock(return_value=mock_chat_obj)
            ) as mock_get_chat,
            patch(
                "areyouok_telegram.handlers.commands.Sessions.get_active_session", new=AsyncMock(return_value=None)
            ) as mock_get_active_session,
            patch(
                "areyouok_telegram.handlers.commands.Sessions.create_session", new=AsyncMock(return_value=mock_session)
            ) as mock_create_session,
            patch(
                "areyouok_telegram.handlers.commands.GuidedSessions.get_by_chat_id", new=AsyncMock(return_value=[])
            ) as mock_get_guided_sessions,
            patch(
                "areyouok_telegram.handlers.commands.GuidedSessions.start_new_session", new=AsyncMock()
            ) as mock_start_guided_session,
            patch("areyouok_telegram.handlers.commands.Messages.new_or_update", new=AsyncMock()) as mock_new_message,
        ):
            mock_session.new_activity = AsyncMock()

            await on_start_command(mock_update, mock_context)

            # Verify database operations
            mock_get_chat.assert_called_once_with(mock_db_session, chat_id=str(mock_telegram_chat.id))
            mock_get_active_session.assert_called_once_with(mock_db_session, chat_id=str(mock_telegram_chat.id))
            mock_create_session.assert_called_once_with(
                mock_db_session, chat_id=str(mock_telegram_chat.id), timestamp=mock_telegram_message.date
            )
            mock_get_guided_sessions.assert_called_once_with(
                mock_db_session,
                chat_id=str(mock_telegram_chat.id),
                session_type="onboarding",
            )
            mock_start_guided_session.assert_called_once_with(
                mock_db_session,
                chat_id=str(mock_telegram_chat.id),
                chat_session=mock_session.session_key,
                session_type="onboarding",
            )
            mock_new_message.assert_called_once_with(
                mock_db_session,
                user_encryption_key="test_encryption_key",
                user_id=mock_telegram_user.id,
                chat_id=mock_telegram_chat.id,
                message=mock_telegram_message,
                session_key=mock_session.session_key,
            )
            mock_session.new_activity.assert_called_once_with(
                mock_db_session, timestamp=mock_telegram_message.date, is_user=True
            )

            # No message should be sent to user
            mock_context.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_start_command_existing_session_no_onboarding(
        self, mock_db_session, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test on_start_command when session exists but no onboarding history."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_chat = mock_telegram_chat
        mock_update.effective_user = mock_telegram_user
        mock_update.message = mock_telegram_message

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Create mock objects
        mock_chat_obj = MagicMock()
        mock_chat_obj.retrieve_key.return_value = "test_encryption_key"

        mock_session = MagicMock()
        mock_session.session_key = "existing_session_key"

        with (
            patch(
                "areyouok_telegram.handlers.commands.Chats.get_by_id", new=AsyncMock(return_value=mock_chat_obj)
            ) as mock_get_chat,
            patch(
                "areyouok_telegram.handlers.commands.Sessions.get_active_session",
                new=AsyncMock(return_value=mock_session),
            ) as mock_get_active_session,
            patch(
                "areyouok_telegram.handlers.commands.Sessions.create_session", new=AsyncMock()
            ) as mock_create_session,
            patch(
                "areyouok_telegram.handlers.commands.GuidedSessions.get_by_chat_id", new=AsyncMock(return_value=[])
            ) as mock_get_guided_sessions,
            patch(
                "areyouok_telegram.handlers.commands.GuidedSessions.start_new_session", new=AsyncMock()
            ) as mock_start_guided_session,
            patch("areyouok_telegram.handlers.commands.Messages.new_or_update", new=AsyncMock()) as mock_new_message,
        ):
            mock_session.new_activity = AsyncMock()

            await on_start_command(mock_update, mock_context)

            # Verify database operations
            mock_get_chat.assert_called_once_with(mock_db_session, chat_id=str(mock_telegram_chat.id))
            mock_get_active_session.assert_called_once_with(mock_db_session, chat_id=str(mock_telegram_chat.id))
            # Should not create new session since one exists
            mock_create_session.assert_not_called()
            mock_get_guided_sessions.assert_called_once_with(
                mock_db_session,
                chat_id=str(mock_telegram_chat.id),
                session_type="onboarding",
            )
            mock_start_guided_session.assert_called_once_with(
                mock_db_session,
                chat_id=str(mock_telegram_chat.id),
                chat_session=mock_session.session_key,
                session_type="onboarding",
            )
            mock_new_message.assert_called_once_with(
                mock_db_session,
                user_encryption_key="test_encryption_key",
                user_id=mock_telegram_user.id,
                chat_id=mock_telegram_chat.id,
                message=mock_telegram_message,
                session_key=mock_session.session_key,
            )
            mock_session.new_activity.assert_called_once_with(
                mock_db_session, timestamp=mock_telegram_message.date, is_user=True
            )

            # No message should be sent to user
            mock_context.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_start_command_completed_onboarding(
        self, mock_db_session, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test on_start_command when user has completed onboarding."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_chat = mock_telegram_chat
        mock_update.effective_user = mock_telegram_user
        mock_update.message = mock_telegram_message

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Create mock objects
        mock_chat_obj = MagicMock()
        mock_chat_obj.retrieve_key.return_value = "test_encryption_key"

        mock_session = MagicMock()
        mock_session.session_key = "test_session_key"

        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_completed = True

        with (
            patch(
                "areyouok_telegram.handlers.commands.Chats.get_by_id", new=AsyncMock(return_value=mock_chat_obj)
            ) as mock_get_chat,
            patch(
                "areyouok_telegram.handlers.commands.Sessions.get_active_session",
                new=AsyncMock(return_value=mock_session),
            ) as mock_get_active_session,
            patch(
                "areyouok_telegram.handlers.commands.Sessions.create_session", new=AsyncMock()
            ) as mock_create_session,
            patch(
                "areyouok_telegram.handlers.commands.GuidedSessions.get_by_chat_id",
                new=AsyncMock(return_value=[mock_onboarding_session]),
            ) as mock_get_guided_sessions,
            patch(
                "areyouok_telegram.handlers.commands.GuidedSessions.start_new_session", new=AsyncMock()
            ) as mock_start_guided_session,
            patch("areyouok_telegram.handlers.commands.Messages.new_or_update", new=AsyncMock()) as mock_new_message,
            patch("areyouok_telegram.handlers.commands.ONBOARDING_COMPLETE_MESSAGE", "Onboarding already completed!"),
        ):
            mock_session.new_activity = AsyncMock()

            await on_start_command(mock_update, mock_context)

            # Verify database operations
            mock_get_chat.assert_called_once_with(mock_db_session, chat_id=str(mock_telegram_chat.id))
            mock_get_active_session.assert_called_once_with(mock_db_session, chat_id=str(mock_telegram_chat.id))
            # Should not create new session since one exists
            mock_create_session.assert_not_called()
            mock_get_guided_sessions.assert_called_once_with(
                mock_db_session,
                chat_id=str(mock_telegram_chat.id),
                session_type="onboarding",
            )
            # Should not start new guided session since onboarding is complete
            mock_start_guided_session.assert_not_called()
            # Should not save message since early return
            mock_new_message.assert_not_called()
            mock_session.new_activity.assert_not_called()

            # Should send completion message to user
            mock_context.bot.send_message.assert_called_once_with(
                chat_id=mock_telegram_chat.id,
                text="Onboarding already completed!",
            )

    @pytest.mark.asyncio
    async def test_on_start_command_incomplete_onboarding(
        self, mock_db_session, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test on_start_command when user has incomplete onboarding session."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_chat = mock_telegram_chat
        mock_update.effective_user = mock_telegram_user
        mock_update.message = mock_telegram_message

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Create mock objects
        mock_chat_obj = MagicMock()
        mock_chat_obj.retrieve_key.return_value = "test_encryption_key"

        mock_session = MagicMock()
        mock_session.session_key = "test_session_key"

        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_completed = False
        mock_onboarding_session.is_incomplete = True

        with (
            patch(
                "areyouok_telegram.handlers.commands.Chats.get_by_id", new=AsyncMock(return_value=mock_chat_obj)
            ) as mock_get_chat,
            patch(
                "areyouok_telegram.handlers.commands.Sessions.get_active_session",
                new=AsyncMock(return_value=mock_session),
            ) as mock_get_active_session,
            patch(
                "areyouok_telegram.handlers.commands.Sessions.create_session", new=AsyncMock()
            ) as mock_create_session,
            patch(
                "areyouok_telegram.handlers.commands.GuidedSessions.get_by_chat_id",
                new=AsyncMock(return_value=[mock_onboarding_session]),
            ) as mock_get_guided_sessions,
            patch(
                "areyouok_telegram.handlers.commands.GuidedSessions.start_new_session", new=AsyncMock()
            ) as mock_start_guided_session,
            patch("areyouok_telegram.handlers.commands.Messages.new_or_update", new=AsyncMock()) as mock_new_message,
        ):
            mock_session.new_activity = AsyncMock()

            await on_start_command(mock_update, mock_context)

            # Verify database operations
            mock_get_chat.assert_called_once_with(mock_db_session, chat_id=str(mock_telegram_chat.id))
            mock_get_active_session.assert_called_once_with(mock_db_session, chat_id=str(mock_telegram_chat.id))
            # Should not create new session since one exists
            mock_create_session.assert_not_called()
            mock_get_guided_sessions.assert_called_once_with(
                mock_db_session,
                chat_id=str(mock_telegram_chat.id),
                session_type="onboarding",
            )
            # Should start new guided session since onboarding is incomplete
            mock_start_guided_session.assert_called_once_with(
                mock_db_session,
                chat_id=str(mock_telegram_chat.id),
                chat_session=mock_session.session_key,
                session_type="onboarding",
            )
            mock_new_message.assert_called_once_with(
                mock_db_session,
                user_encryption_key="test_encryption_key",
                user_id=mock_telegram_user.id,
                chat_id=mock_telegram_chat.id,
                message=mock_telegram_message,
                session_key=mock_session.session_key,
            )
            mock_session.new_activity.assert_called_once_with(
                mock_db_session, timestamp=mock_telegram_message.date, is_user=True
            )

            # No message should be sent to user
            mock_context.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_start_command_onboarding_session_not_incomplete(
        self, mock_db_session, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test on_start_command when existing onboarding session is neither completed nor incomplete."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_chat = mock_telegram_chat
        mock_update.effective_user = mock_telegram_user
        mock_update.message = mock_telegram_message

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Create mock objects
        mock_chat_obj = MagicMock()
        mock_chat_obj.retrieve_key.return_value = "test_encryption_key"

        mock_session = MagicMock()
        mock_session.session_key = "test_session_key"

        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_completed = False
        mock_onboarding_session.is_incomplete = False  # Neither completed nor incomplete

        with (
            patch(
                "areyouok_telegram.handlers.commands.Chats.get_by_id", new=AsyncMock(return_value=mock_chat_obj)
            ) as mock_get_chat,
            patch(
                "areyouok_telegram.handlers.commands.Sessions.get_active_session",
                new=AsyncMock(return_value=mock_session),
            ) as mock_get_active_session,
            patch(
                "areyouok_telegram.handlers.commands.Sessions.create_session", new=AsyncMock()
            ) as mock_create_session,
            patch(
                "areyouok_telegram.handlers.commands.GuidedSessions.get_by_chat_id",
                new=AsyncMock(return_value=[mock_onboarding_session]),
            ) as mock_get_guided_sessions,
            patch(
                "areyouok_telegram.handlers.commands.GuidedSessions.start_new_session", new=AsyncMock()
            ) as mock_start_guided_session,
            patch("areyouok_telegram.handlers.commands.Messages.new_or_update", new=AsyncMock()) as mock_new_message,
        ):
            mock_session.new_activity = AsyncMock()

            await on_start_command(mock_update, mock_context)

            # Verify database operations
            mock_get_chat.assert_called_once_with(mock_db_session, chat_id=str(mock_telegram_chat.id))
            mock_get_active_session.assert_called_once_with(mock_db_session, chat_id=str(mock_telegram_chat.id))
            # Should not create new session since one exists
            mock_create_session.assert_not_called()
            mock_get_guided_sessions.assert_called_once_with(
                mock_db_session,
                chat_id=str(mock_telegram_chat.id),
                session_type="onboarding",
            )
            # Should not start new guided session since onboarding is not incomplete
            mock_start_guided_session.assert_not_called()
            mock_new_message.assert_called_once_with(
                mock_db_session,
                user_encryption_key="test_encryption_key",
                user_id=mock_telegram_user.id,
                chat_id=mock_telegram_chat.id,
                message=mock_telegram_message,
                session_key=mock_session.session_key,
            )
            mock_session.new_activity.assert_called_once_with(
                mock_db_session, timestamp=mock_telegram_message.date, is_user=True
            )

            # No message should be sent to user
            mock_context.bot.send_message.assert_not_called()


class TestOnEndCommand:
    """Test the on_end_command handler."""

    @pytest.mark.asyncio
    async def test_on_end_command_returns_none(self):
        """Test on_end_command just returns None."""
        # Create mock update and context
        mock_update = MagicMock(spec=telegram.Update)
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Call the handler
        result = await on_end_command(mock_update, mock_context)

        # Should return None
        assert result is None
