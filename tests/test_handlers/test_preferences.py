"""Tests for handlers/preferences.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.handlers.commands.preferences import on_preferences_command


class TestOnPreferencesCommand:
    """Test the on_preferences_command handler."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.CommandUsage.save")
    @patch("areyouok_telegram.data.models.Session.get_or_create_new_session")
    @patch("areyouok_telegram.handlers.commands.preferences._construct_user_preferences_response")
    async def test_on_preferences_command_display_preferences(
        self,
        mock_construct_response,
        mock_get_session,
        mock_track_usage,
        mock_telegram_user,
        mock_telegram_chat,
        mock_telegram_message,
    ):
        """Test preferences command displays current preferences when no arguments provided."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/preferences"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        mock_get_session.return_value = mock_session
        mock_track_usage.return_value = None

        mock_construct_response.return_value = "**Your Current Preferences:**\n• Name: John Doe"

        # Call handler
        await on_preferences_command(mock_update, mock_context)

        # Verify preferences response was constructed
        mock_construct_response.assert_called_once_with(user_id=str(mock_telegram_user.id))

        # Verify message was sent
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=mock_telegram_chat.id,
            text="**Your Current Preferences:**\n• Name: John Doe",
            parse_mode="MarkdownV2",
        )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.commands.preferences._update_user_metadata_field")
    @patch("areyouok_telegram.data.models.Session.get_or_create_new_session")
    async def test_on_preferences_command_update_preferred_name(
        self,
        mock_get_active_session,
        mock_update_field,
        mock_telegram_user,
        mock_telegram_chat,
        mock_telegram_message,
    ):
        """Test preferences command updates preferred name field."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/preferences name Alice Smith"
        mock_update.message.message_id = 12345

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = 123
        mock_get_active_session.return_value = mock_session

        # Mock update response
        mock_response = MagicMock()
        mock_response.feedback = "Successfully updated your preferred name to Alice Smith."
        mock_update_field.return_value = mock_response

        # Call handler
        await on_preferences_command(mock_update, mock_context)

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

        # Verify session was created/retrieved
        mock_get_active_session.assert_called_once_with(
            chat_id=str(mock_telegram_chat.id),
            timestamp=mock_telegram_message.date,
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
    @patch("areyouok_telegram.handlers.commands.preferences._update_user_metadata_field")
    @patch("areyouok_telegram.data.models.Session.get_or_create_new_session")
    async def test_on_preferences_command_update_country(
        self,
        mock_get_active_session,
        mock_update_field,
        mock_telegram_user,
        mock_telegram_chat,
        mock_telegram_message,
    ):
        """Test preferences command updates country field."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/preferences country USA"
        mock_update.message.message_id = 12345

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = 123
        mock_get_active_session.return_value = mock_session

        # Mock update response
        mock_response = MagicMock()
        mock_response.feedback = "Successfully updated your country to USA."
        mock_update_field.return_value = mock_response

        # Call handler
        await on_preferences_command(mock_update, mock_context)

        # Verify field update was called with correct parameters
        mock_update_field.assert_called_once_with(
            chat_id=str(mock_telegram_chat.id),
            session_id=str(mock_session.session_id),
            field_name="country",
            new_value="USA",
        )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.commands.preferences._update_user_metadata_field")
    @patch("areyouok_telegram.data.models.Session.get_or_create_new_session")
    async def test_on_preferences_command_update_timezone(
        self,
        mock_get_active_session,
        mock_update_field,
        mock_telegram_user,
        mock_telegram_chat,
        mock_telegram_message,
    ):
        """Test preferences command updates timezone field."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/preferences timezone America/New_York"
        mock_update.message.message_id = 12345

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = 123
        mock_get_active_session.return_value = mock_session

        # Mock update response
        mock_response = MagicMock()
        mock_response.feedback = "Successfully updated your timezone to America/New_York."
        mock_update_field.return_value = mock_response

        # Call handler
        await on_preferences_command(mock_update, mock_context)

        # Verify field update was called with correct parameters
        mock_update_field.assert_called_once_with(
            chat_id=str(mock_telegram_chat.id),
            session_id=str(mock_session.session_id),
            field_name="timezone",
            new_value="America/New_York",
        )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.CommandUsage.save")
    @patch("areyouok_telegram.data.models.Session.get_or_create_new_session")
    async def test_on_preferences_command_invalid_field(
        self,
        mock_get_session,
        mock_track_usage,
        mock_telegram_user,
        mock_telegram_chat,
        mock_telegram_message,
    ):
        """Test preferences command with invalid field name."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/preferences invalid_field some_value"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        mock_get_session.return_value = mock_session
        mock_track_usage.return_value = None

        # Call handler
        await on_preferences_command(mock_update, mock_context)

        # Verify error message was sent
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=mock_telegram_chat.id,
            text="Invalid field. Please specify one of: name, country, timezone.",
        )

    @pytest.mark.asyncio
    async def test_on_preferences_command_field_normalization(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test that 'name' field is normalized to 'preferred_name'."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/preferences name Alice"  # Use 'name' to test normalization
        mock_update.message.message_id = 12345

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        with (
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session"
            ) as mock_get_active_session,
            patch("areyouok_telegram.handlers.commands.preferences._update_user_metadata_field") as mock_update_field,
        ):
            # Mock session
            mock_session = MagicMock()
            mock_session.session_id = 123
            mock_get_active_session.return_value = mock_session

            # Mock update response
            mock_response = MagicMock()
            mock_response.feedback = "Updated."
            mock_update_field.return_value = mock_response

            # Call handler
            await on_preferences_command(mock_update, mock_context)

            # Verify the field name was normalized from 'name' to 'preferred_name'
            mock_update_field.assert_called_once_with(
                chat_id=str(mock_telegram_chat.id),
                session_id=str(mock_session.session_id),
                field_name="preferred_name",
                new_value="Alice",
            )
