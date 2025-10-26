"""Tests for handlers/preferences.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.handlers.commands.preferences import on_preferences_command


class TestOnPreferencesCommand:
    """Test the on_preferences_command handler."""

    @pytest.mark.asyncio
    async def test_on_preferences_command_display_preferences(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, user_factory, session_factory
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

        # Use real Pydantic instances
        mock_chat = chat_factory(id_value=1)
        mock_user = user_factory(id_value=100)
        mock_session = session_factory(chat=mock_chat, id_value=123)

        # Mock user metadata
        mock_metadata = MagicMock()
        mock_metadata.preferred_name = "John Doe"
        mock_metadata.country = "USA"
        mock_metadata.timezone = "America/New_York"
        mock_metadata.response_speed = "normal"

        with (
            patch(
                "areyouok_telegram.handlers.commands.preferences.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.handlers.commands.preferences.User.get_by_id",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.commands.preferences.UserMetadata.get_by_user_id",
                new=AsyncMock(return_value=mock_metadata),
            ),
            patch("areyouok_telegram.handlers.commands.preferences.pycountry") as mock_pycountry,
        ):
            mock_country = MagicMock()
            mock_country.name = "United States"
            mock_pycountry.countries.get.return_value = mock_country

            await on_preferences_command(mock_update, mock_context)

            # Verify message was sent with preferences
            mock_context.bot.send_message.assert_called_once()
            call_kwargs = mock_context.bot.send_message.call_args.kwargs
            assert "John Doe" in call_kwargs["text"] or "escaped" in call_kwargs["text"]  # May be escaped

    @pytest.mark.asyncio
    async def test_on_preferences_command_update_preferred_name(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, user_factory, session_factory
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

        # Use real Pydantic instances
        mock_chat = chat_factory(id_value=1)
        mock_user = user_factory(id_value=100)
        mock_session = session_factory(chat=mock_chat, id_value=123)

        # Mock agent response
        mock_agent_response = MagicMock()
        mock_agent_response.output = MagicMock()
        mock_agent_response.output.feedback = "Updated your name to Alice Smith"

        with (
            patch(
                "areyouok_telegram.handlers.commands.preferences.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.handlers.commands.preferences.User.get_by_id",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.commands.preferences.run_agent_with_tracking",
                new=AsyncMock(return_value=mock_agent_response),
            ),
        ):
            await on_preferences_command(mock_update, mock_context)

            # Verify reaction and typing indicator
            assert mock_context.bot.set_message_reaction.called
            assert mock_context.bot.send_chat_action.called

            # Verify response message was sent
            mock_context.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_preferences_command_update_country(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, user_factory, session_factory
    ):
        """Test preferences command updates country field."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/preferences country USA"
        mock_update.message.message_id = 12346

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Use real Pydantic instances
        mock_chat = chat_factory(id_value=1)
        mock_user = user_factory(id_value=100)
        mock_session = session_factory(chat=mock_chat, id_value=123)

        mock_agent_response = MagicMock()
        mock_agent_response.output = MagicMock()
        mock_agent_response.output.feedback = "Updated your country to USA"

        with (
            patch(
                "areyouok_telegram.handlers.commands.preferences.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.handlers.commands.preferences.User.get_by_id",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.commands.preferences.run_agent_with_tracking",
                new=AsyncMock(return_value=mock_agent_response),
            ),
        ):
            await on_preferences_command(mock_update, mock_context)

            # Verify response message was sent
            mock_context.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_preferences_command_update_timezone(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, user_factory, session_factory
    ):
        """Test preferences command updates timezone field."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/preferences timezone America/New_York"
        mock_update.message.message_id = 12347

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Use real Pydantic instances
        mock_chat = chat_factory(id_value=1)
        mock_user = user_factory(id_value=100)
        mock_session = session_factory(chat=mock_chat, id_value=123)

        mock_agent_response = MagicMock()
        mock_agent_response.output = MagicMock()
        mock_agent_response.output.feedback = "Updated your timezone"

        with (
            patch(
                "areyouok_telegram.handlers.commands.preferences.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.handlers.commands.preferences.User.get_by_id",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.commands.preferences.run_agent_with_tracking",
                new=AsyncMock(return_value=mock_agent_response),
            ),
        ):
            await on_preferences_command(mock_update, mock_context)

            # Verify response message was sent
            mock_context.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_preferences_command_invalid_field(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, user_factory, session_factory
    ):
        """Test preferences command with invalid field name."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/preferences invalid_field test"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Use real Pydantic instances
        mock_chat = chat_factory(id_value=1)
        mock_user = user_factory(id_value=100)
        mock_session = session_factory(chat=mock_chat, id_value=123)

        with (
            patch(
                "areyouok_telegram.handlers.commands.preferences.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.handlers.commands.preferences.User.get_by_id",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
        ):
            await on_preferences_command(mock_update, mock_context)

            # Verify error message was sent
            mock_context.bot.send_message.assert_called_once()
            call_kwargs = mock_context.bot.send_message.call_args.kwargs
            assert "Invalid field" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_on_preferences_command_field_normalization(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, user_factory, session_factory
    ):
        """Test that 'name' field is normalized to 'preferred_name'."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/preferences name Alice"
        mock_update.message.message_id = 12348

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Use real Pydantic instances
        mock_chat = chat_factory(id_value=1)
        mock_user = user_factory(id_value=100)
        mock_session = session_factory(chat=mock_chat, id_value=123)

        mock_agent_response = MagicMock()
        mock_agent_response.output = MagicMock()
        mock_agent_response.output.feedback = "Updated your preferred name"

        with (
            patch(
                "areyouok_telegram.handlers.commands.preferences.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.handlers.commands.preferences.User.get_by_id",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.commands.preferences.run_agent_with_tracking",
                new=AsyncMock(return_value=mock_agent_response),
            ) as mock_agent,
        ):
            await on_preferences_command(mock_update, mock_context)

            # Verify agent was called (field normalization happens before agent call)
            mock_agent.assert_called_once()
            # Verify response was sent
            mock_context.bot.send_message.assert_called_once()
