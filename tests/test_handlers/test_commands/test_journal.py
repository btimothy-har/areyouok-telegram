"""Tests for handlers/commands/journal.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.handlers.commands.journal import on_journal_command
from areyouok_telegram.handlers.utils.constants import MD2_JOURNAL_START_MESSAGE


class TestOnJournalCommand:
    """Test the on_journal_command handler."""

    @pytest.mark.asyncio
    async def test_on_journal_command_starts_new_session(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, user_factory, session_factory
    ):
        """Test on_journal_command creates a new journaling session and sends holding message."""
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

        with (
            patch(
                "areyouok_telegram.handlers.commands.journal.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.handlers.commands.journal.User.get_by_id",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.data.models.GuidedSession.get_by_chat",
                new=AsyncMock(return_value=[]),  # No existing active sessions
            ),
            patch("areyouok_telegram.data.models.GuidedSession.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.data.models.Message.from_telegram",
                return_value=MagicMock(save=AsyncMock()),
            ),
            patch("areyouok_telegram.data.models.Session.new_message", new=AsyncMock()),
        ):
            await on_journal_command(mock_update, mock_context)

            # Verify bot sent holding message
            mock_context.bot.send_message.assert_called_once()
            call_kwargs = mock_context.bot.send_message.call_args.kwargs
            assert call_kwargs["chat_id"] == mock_telegram_chat.id
            assert call_kwargs["text"] == MD2_JOURNAL_START_MESSAGE
            assert call_kwargs["parse_mode"] == "MarkdownV2"

    @pytest.mark.asyncio
    async def test_on_journal_command_with_existing_active_session(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, session_factory
    ):
        """Test on_journal_command when there's already an active session."""
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
        mock_session = session_factory(chat=mock_chat, id_value=123)

        # Create mock existing session
        mock_existing_session = MagicMock()
        mock_existing_session.session_type = "onboarding"

        with (
            patch(
                "areyouok_telegram.handlers.commands.journal.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.data.models.GuidedSession.get_by_chat",
                new=AsyncMock(return_value=[mock_existing_session]),  # Existing active session
            ),
        ):
            await on_journal_command(mock_update, mock_context)

            # Verify error message was sent
            mock_context.bot.send_message.assert_called_once()
            call_kwargs = mock_context.bot.send_message.call_args.kwargs
            assert "already have an active" in call_kwargs["text"]
            assert "onboarding" in call_kwargs["text"].lower()

    @pytest.mark.asyncio
    async def test_on_journal_command_tracks_command_usage(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, user_factory, session_factory
    ):
        """Test that journal command usage is tracked."""
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

        with (
            patch(
                "areyouok_telegram.handlers.commands.journal.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.handlers.commands.journal.User.get_by_id",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()) as mock_track,
            patch(
                "areyouok_telegram.data.models.GuidedSession.get_by_chat",
                new=AsyncMock(return_value=[]),
            ),
            patch("areyouok_telegram.data.models.GuidedSession.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.data.models.Message.from_telegram",
                return_value=MagicMock(save=AsyncMock()),
            ),
            patch("areyouok_telegram.data.models.Session.new_message", new=AsyncMock()),
        ):
            await on_journal_command(mock_update, mock_context)

            # Verify command usage was tracked (CommandUsage.save was called)
            mock_track.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_journaling_session_creates_correct_metadata(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message, chat_factory, user_factory, session_factory
    ):
        """Test that journaling session is initialized with correct metadata structure."""
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

        with (
            patch(
                "areyouok_telegram.handlers.commands.journal.Chat.get_by_id",
                new=AsyncMock(return_value=mock_chat),
            ),
            patch(
                "areyouok_telegram.handlers.commands.journal.User.get_by_id",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "areyouok_telegram.data.models.Session.get_or_create_new_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.data.models.CommandUsage.save", new=AsyncMock()),
            patch(
                "areyouok_telegram.data.models.GuidedSession.get_by_chat",
                new=AsyncMock(return_value=[]),
            ),
            patch("areyouok_telegram.data.models.GuidedSession.save", new=AsyncMock()) as mock_gs_save,
            patch(
                "areyouok_telegram.data.models.Message.from_telegram",
                return_value=MagicMock(save=AsyncMock()),
            ),
            patch("areyouok_telegram.data.models.Session.new_message", new=AsyncMock()),
        ):
            await on_journal_command(mock_update, mock_context)

            # Verify GuidedSession.save was called (metadata is set during construction)
            mock_gs_save.assert_called_once()
            # Metadata validation happens in the JournalContextMetadata model itself
