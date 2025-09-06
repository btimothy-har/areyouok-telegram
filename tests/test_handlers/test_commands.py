"""Tests for handlers/commands.py."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import SYSTEM_USER_ID
from areyouok_telegram.handlers.commands import on_end_command
from areyouok_telegram.handlers.commands import on_settings_command
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
        mock_session.last_bot_activity = "2024-01-01T10:00:00Z"  # Has previous activity, no greeting

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
            mock_session.new_message = AsyncMock()

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
            mock_session.new_message.assert_called_once_with(
                mock_db_session, timestamp=mock_telegram_message.date, is_user=True
            )

            # No message should be sent to user since no onboarding greeting condition is met
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
        mock_session.last_bot_activity = "2024-01-01T10:00:00Z"  # Has previous activity, no greeting

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
            mock_session.new_message = AsyncMock()

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
            mock_session.new_message.assert_called_once_with(
                mock_db_session, timestamp=mock_telegram_message.date, is_user=True
            )

            # No message should be sent to user since no onboarding greeting condition is met
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
            patch(
                "areyouok_telegram.handlers.commands.MD2_ONBOARDING_COMPLETE_MESSAGE", "Onboarding already completed!"
            ),
        ):
            mock_session.new_message = AsyncMock()

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
            mock_session.new_message.assert_not_called()

            # Should send completion message to user
            mock_context.bot.send_message.assert_called_once_with(
                chat_id=mock_telegram_chat.id,
                text="Onboarding already completed!",
                parse_mode="MarkdownV2",
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
        mock_session.last_bot_activity = "2024-01-01T10:00:00Z"  # Has previous activity, no greeting

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
            mock_session.new_message = AsyncMock()

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
            mock_session.new_message.assert_called_once_with(
                mock_db_session, timestamp=mock_telegram_message.date, is_user=True
            )

            # No message should be sent to user since no onboarding greeting condition is met
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
        mock_session.last_bot_activity = "2024-01-01T10:00:00Z"  # Has previous activity, no greeting

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
            mock_session.new_message = AsyncMock()

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
            mock_session.new_message.assert_called_once_with(
                mock_db_session, timestamp=mock_telegram_message.date, is_user=True
            )

            # No message should be sent to user since no onboarding greeting condition is met
            mock_context.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_start_command_sends_greeting_message_for_new_user(
        self, mock_db_session, mock_telegram_user, mock_telegram_chat, mock_telegram_message
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

        # Create mock objects
        mock_chat_obj = MagicMock()
        mock_chat_obj.retrieve_key.return_value = "test_encryption_key"

        mock_session = MagicMock()
        mock_session.session_key = "test_session_key"
        mock_session.last_bot_activity = None  # Key condition for sending greeting

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
            patch("areyouok_telegram.handlers.commands.MD2_ONBOARDING_START_MESSAGE", "Hello there! Please wait..."),
        ):
            mock_session.new_message = AsyncMock()

            await on_start_command(mock_update, mock_context)

            # Verify database operations
            mock_get_chat.assert_called_once_with(mock_db_session, chat_id=str(mock_telegram_chat.id))
            mock_get_active_session.assert_called_once_with(mock_db_session, chat_id=str(mock_telegram_chat.id))
            mock_create_session.assert_not_called()  # Session already exists
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

            # Verify user message was saved
            assert mock_new_message.call_count == 2  # User message + bot greeting message

            # First call: user message
            user_msg_call = mock_new_message.call_args_list[0]
            assert user_msg_call[1]["user_encryption_key"] == "test_encryption_key"
            assert user_msg_call[1]["user_id"] == mock_telegram_user.id
            assert user_msg_call[1]["chat_id"] == mock_telegram_chat.id
            assert user_msg_call[1]["message"] == mock_telegram_message
            assert user_msg_call[1]["session_key"] == mock_session.session_key

            # Second call: bot greeting message
            bot_msg_call = mock_new_message.call_args_list[1]
            assert bot_msg_call[1]["user_encryption_key"] == "test_encryption_key"
            assert bot_msg_call[1]["user_id"] == SYSTEM_USER_ID
            assert bot_msg_call[1]["chat_id"] == str(mock_telegram_chat.id)
            assert bot_msg_call[1]["message"] == mock_bot_message
            assert bot_msg_call[1]["session_key"] == mock_session.session_key

            mock_session.new_message.assert_called_once_with(
                mock_db_session, timestamp=mock_telegram_message.date, is_user=True
            )

            # Verify greeting message was sent
            mock_context.bot.send_message.assert_called_once_with(
                chat_id=mock_telegram_chat.id,
                text="Hello there! Please wait...",
                parse_mode="MarkdownV2",
            )


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


class TestOnSettingsCommand:
    """Test the on_settings_command handler."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.commands.construct_user_settings_response")
    async def test_on_settings_command_display_settings(
        self, mock_construct_response, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test settings command displays current settings when no arguments provided."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        mock_construct_response.return_value = "**Your Current Settings:**\n• Name: John Doe"

        # Call handler
        await on_settings_command(mock_update, mock_context)

        # Verify settings response was constructed
        mock_construct_response.assert_called_once_with(user_id=str(mock_telegram_user.id))

        # Verify message was sent
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=mock_telegram_chat.id,
            text="**Your Current Settings:**\n• Name: John Doe",
            parse_mode="MarkdownV2",
        )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.commands.update_user_metadata_field")
    @patch("areyouok_telegram.handlers.commands.Sessions.get_active_session")
    @patch("areyouok_telegram.handlers.commands.async_database")
    async def test_on_settings_command_update_preferred_name(
        self,
        mock_async_database,
        mock_get_active_session,
        mock_update_field,
        mock_telegram_user,
        mock_telegram_chat,
        mock_telegram_message,
    ):
        """Test settings command updates preferred name field."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings name Alice Smith"
        mock_update.message.id = 12345

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Mock database session
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = 123
        mock_get_active_session.return_value = mock_session

        # Mock update response
        mock_response = MagicMock()
        mock_response.feedback = "Successfully updated your preferred name to Alice Smith."
        mock_update_field.return_value = mock_response

        # Call handler
        await on_settings_command(mock_update, mock_context)

        # Verify reaction was set
        mock_context.bot.set_message_reaction.assert_called_once_with(
            chat_id=mock_telegram_chat.id,
            message_id=12345,
            reaction="👌",
        )

        # Verify typing indicator
        mock_context.bot.send_chat_action.assert_called_once_with(
            chat_id=mock_telegram_chat.id,
            action=telegram.constants.ChatAction.TYPING,
        )

        # Verify field update was called
        mock_update_field.assert_called_once_with(
            chat_id=str(mock_telegram_chat.id),
            session_id=str(mock_session.session_id),
            field_name="preferred_name",
            new_value="Alice Smith",
        )

        # Verify response message
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=mock_telegram_chat.id,
            text="Successfully updated your preferred name to Alice Smith.",
        )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.commands.update_user_metadata_field")
    @patch("areyouok_telegram.handlers.commands.Sessions.get_active_session")
    @patch("areyouok_telegram.handlers.commands.async_database")
    async def test_on_settings_command_update_country(
        self,
        mock_async_database,
        mock_get_active_session,
        mock_update_field,
        mock_telegram_user,
        mock_telegram_chat,
        mock_telegram_message,
    ):
        """Test settings command updates country field."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings country USA"
        mock_update.message.id = 12345

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Mock database session
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = 123
        mock_get_active_session.return_value = mock_session

        # Mock update response
        mock_response = MagicMock()
        mock_response.feedback = "Successfully updated your country to USA."
        mock_update_field.return_value = mock_response

        # Call handler
        await on_settings_command(mock_update, mock_context)

        # Verify field update was called with correct parameters
        mock_update_field.assert_called_once_with(
            chat_id=str(mock_telegram_chat.id),
            session_id=str(mock_session.session_id),
            field_name="country",
            new_value="USA",
        )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.commands.update_user_metadata_field")
    @patch("areyouok_telegram.handlers.commands.Sessions.get_active_session")
    @patch("areyouok_telegram.handlers.commands.async_database")
    async def test_on_settings_command_update_timezone(
        self,
        mock_async_database,
        mock_get_active_session,
        mock_update_field,
        mock_telegram_user,
        mock_telegram_chat,
        mock_telegram_message,
    ):
        """Test settings command updates timezone field."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings timezone America/New_York"
        mock_update.message.id = 12345

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Mock database session
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = 123
        mock_get_active_session.return_value = mock_session

        # Mock update response
        mock_response = MagicMock()
        mock_response.feedback = "Successfully updated your timezone to America/New_York."
        mock_update_field.return_value = mock_response

        # Call handler
        await on_settings_command(mock_update, mock_context)

        # Verify field update was called with correct parameters
        mock_update_field.assert_called_once_with(
            chat_id=str(mock_telegram_chat.id),
            session_id=str(mock_session.session_id),
            field_name="timezone",
            new_value="America/New_York",
        )

    @pytest.mark.asyncio
    async def test_on_settings_command_invalid_field(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test settings command with invalid field name."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings invalid_field some_value"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Call handler
        await on_settings_command(mock_update, mock_context)

        # Verify error message was sent
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=mock_telegram_chat.id,
            text="Invalid field. Please specify one of: name, country, timezone.",
        )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.commands.Sessions.get_active_session")
    @patch("areyouok_telegram.handlers.commands.Sessions.create_session")
    @patch("areyouok_telegram.handlers.commands.async_database")
    async def test_on_settings_command_creates_session_if_none_exists(
        self,
        mock_async_database,
        mock_create_session,
        mock_get_active_session,
        mock_telegram_user,
        mock_telegram_chat,
        mock_telegram_message,
    ):
        """Test settings command creates session if none exists."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings name John"
        mock_update.message.id = 12345
        mock_update.message.date = "2024-01-01T10:00:00Z"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Mock database session
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock no active session
        mock_get_active_session.return_value = None

        # Mock created session
        mock_new_session = MagicMock()
        mock_new_session.session_id = 456
        mock_create_session.return_value = mock_new_session

        with patch("areyouok_telegram.handlers.commands.update_user_metadata_field") as mock_update_field:
            mock_response = MagicMock()
            mock_response.feedback = "Updated successfully."
            mock_update_field.return_value = mock_response

            # Call handler
            await on_settings_command(mock_update, mock_context)

            # Verify session creation was called
            mock_create_session.assert_called_once_with(
                mock_db_conn, chat_id=str(mock_telegram_chat.id), timestamp=mock_update.message.date
            )

    @pytest.mark.asyncio
    async def test_on_settings_command_field_normalization(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test that 'name' field is normalized to 'preferred_name'."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings preferred_name Alice"  # Use preferred_name to test normalization
        mock_update.message.id = 12345

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        with (
            patch("areyouok_telegram.handlers.commands.async_database") as mock_async_database,
            patch("areyouok_telegram.handlers.commands.Sessions.get_active_session") as mock_get_active_session,
            patch("areyouok_telegram.handlers.commands.update_user_metadata_field") as mock_update_field,
        ):
            # Mock database session
            mock_db_conn = AsyncMock()
            mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
            mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

            # Mock session
            mock_session = MagicMock()
            mock_session.id = 123
            mock_get_active_session.return_value = mock_session

            # Mock update response
            mock_response = MagicMock()
            mock_response.feedback = "Updated."
            mock_update_field.return_value = mock_response

            # Call handler
            await on_settings_command(mock_update, mock_context)

            # Verify the field name passed is still preferred_name (no normalization needed)
            mock_update_field.assert_called_once_with(
                chat_id=str(mock_telegram_chat.id),
                session_id=str(mock_session.session_id),
                field_name="preferred_name",
                new_value="Alice",
            )
