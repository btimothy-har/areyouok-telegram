"""Tests for handlers/commands/journal.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import JournalContextMetadata
from areyouok_telegram.handlers.commands.journal import on_journal_command
from areyouok_telegram.handlers.constants import MD2_JOURNAL_START_MESSAGE


class TestOnJournalCommand:
    """Test the on_journal_command handler."""

    @pytest.mark.asyncio
    async def test_on_journal_command_starts_new_session(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
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

        # Create mock session
        mock_session = MagicMock()
        mock_session.session_id = "test_session_id"

        # Create mock journaling session
        mock_journaling_session = MagicMock()
        mock_journaling_session.update_metadata = AsyncMock()

        # Create mock result for execute
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_journaling_session])
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        with (
            patch(
                "areyouok_telegram.handlers.commands.journal.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.handlers.commands.journal.data_operations.track_command_usage", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.commands.journal.data_operations.get_active_guided_sessions",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.handlers.commands.journal.data_operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch("areyouok_telegram.handlers.commands.journal.data_operations.new_session_event", new=AsyncMock()),
            patch("areyouok_telegram.handlers.commands.journal.async_database") as mock_async_database,
            patch(
                "areyouok_telegram.handlers.commands.journal.GuidedSessions.start_new_session",
                new=AsyncMock(),
            ),
            patch(
                "areyouok_telegram.handlers.commands.journal.GuidedSessions.get_by_chat_session",
                new=AsyncMock(return_value=[mock_journaling_session]),
            ),
        ):
            # Setup database context manager
            mock_db_conn = AsyncMock()
            mock_db_conn.execute = AsyncMock(return_value=mock_result)
            mock_async_database.return_value.__aenter__.return_value = mock_db_conn

            # Mock the is_active property
            type(mock_journaling_session).is_active = MagicMock(return_value=True)

            await on_journal_command(mock_update, mock_context)

            # Verify bot sent holding message
            assert mock_context.bot.send_message.called
            call_kwargs = mock_context.bot.send_message.call_args.kwargs

            assert call_kwargs["chat_id"] == mock_telegram_chat.id
            assert call_kwargs["text"] == MD2_JOURNAL_START_MESSAGE
            assert call_kwargs["parse_mode"] == "MarkdownV2"

            # Verify session was initialized
            mock_journaling_session.update_metadata.assert_called_once()
            metadata = mock_journaling_session.update_metadata.call_args.kwargs["metadata"]
            assert metadata["phase"] == "topic_selection"
            assert metadata["generated_topics"] == []
            assert metadata["selected_topic"] is None

    @pytest.mark.asyncio
    async def test_on_journal_command_with_existing_active_session(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
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

        # Create mock session
        mock_session = MagicMock()
        mock_session.session_id = "test_session_id"

        # Create mock existing session
        mock_existing_session = MagicMock()
        mock_existing_session.session_type = "onboarding"

        with (
            patch(
                "areyouok_telegram.handlers.commands.journal.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.handlers.commands.journal.data_operations.track_command_usage", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.commands.journal.data_operations.get_active_guided_sessions",
                new=AsyncMock(return_value=[mock_existing_session]),
            ),
        ):
            await on_journal_command(mock_update, mock_context)

            # Verify bot sent message about existing session
            assert mock_context.bot.send_message.called
            call_kwargs = mock_context.bot.send_message.call_args.kwargs

            assert call_kwargs["chat_id"] == mock_telegram_chat.id
            assert "already have an active" in call_kwargs["text"].lower()
            assert "onboarding" in call_kwargs["text"].lower()

    @pytest.mark.asyncio
    async def test_on_journal_command_tracks_command_usage(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test on_journal_command tracks command usage."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_chat = mock_telegram_chat
        mock_update.effective_user = mock_telegram_user
        mock_update.message = mock_telegram_message

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Create mock session
        mock_session = MagicMock()
        mock_session.session_id = "test_session_id"

        # Create mock journaling session
        mock_journaling_session = MagicMock()
        mock_journaling_session.update_metadata = AsyncMock()

        # Create mock result for execute
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_journaling_session])
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        with (
            patch(
                "areyouok_telegram.handlers.commands.journal.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch(
                "areyouok_telegram.handlers.commands.journal.data_operations.track_command_usage", new=AsyncMock()
            ) as mock_track,
            patch(
                "areyouok_telegram.handlers.commands.journal.data_operations.get_active_guided_sessions",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.handlers.commands.journal.data_operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_key"),
            ),
            patch("areyouok_telegram.handlers.commands.journal.data_operations.new_session_event", new=AsyncMock()),
            patch("areyouok_telegram.handlers.commands.journal.async_database") as mock_async_database,
            patch(
                "areyouok_telegram.handlers.commands.journal.GuidedSessions.start_new_session",
                new=AsyncMock(),
            ),
            patch(
                "areyouok_telegram.handlers.commands.journal.GuidedSessions.get_by_chat_session",
                new=AsyncMock(return_value=[mock_journaling_session]),
            ),
        ):
            # Setup database context manager
            mock_db_conn = AsyncMock()
            mock_db_conn.execute = AsyncMock(return_value=mock_result)
            mock_async_database.return_value.__aenter__.return_value = mock_db_conn

            # Mock the is_active property
            type(mock_journaling_session).is_active = MagicMock(return_value=True)

            await on_journal_command(mock_update, mock_context)

            # Verify command usage was tracked
            mock_track.assert_called_once_with(
                command="journal",
                chat_id=str(mock_telegram_chat.id),
                session_id=mock_session.session_id,
            )

    @pytest.mark.asyncio
    async def test_initialize_journaling_session_creates_correct_metadata(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test initialize_journaling_session creates metadata with correct structure."""
        # Create mock update
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_chat = mock_telegram_chat
        mock_update.effective_user = mock_telegram_user
        mock_update.message = mock_telegram_message

        # Create mock context
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Create mock session
        mock_session = MagicMock()
        mock_session.session_id = "test_session_id"

        # Create mock journaling session
        mock_journaling_session = MagicMock()
        mock_journaling_session.update_metadata = AsyncMock()

        # Create mock result for execute
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_journaling_session])
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        with (
            patch(
                "areyouok_telegram.handlers.commands.journal.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("areyouok_telegram.handlers.commands.journal.data_operations.track_command_usage", new=AsyncMock()),
            patch(
                "areyouok_telegram.handlers.commands.journal.data_operations.get_active_guided_sessions",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.handlers.commands.journal.data_operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_key"),
            ),
            patch("areyouok_telegram.handlers.commands.journal.data_operations.new_session_event", new=AsyncMock()),
            patch("areyouok_telegram.handlers.commands.journal.async_database") as mock_async_database,
            patch(
                "areyouok_telegram.handlers.commands.journal.GuidedSessions.start_new_session",
                new=AsyncMock(),
            ),
            patch(
                "areyouok_telegram.handlers.commands.journal.GuidedSessions.get_by_chat_session",
                new=AsyncMock(return_value=[mock_journaling_session]),
            ),
        ):
            # Setup database context manager
            mock_db_conn = AsyncMock()
            mock_db_conn.execute = AsyncMock(return_value=mock_result)
            mock_async_database.return_value.__aenter__.return_value = mock_db_conn

            # Mock the is_active property
            type(mock_journaling_session).is_active = MagicMock(return_value=True)

            await on_journal_command(mock_update, mock_context)

            # Verify metadata structure matches JournalContextMetadata
            mock_journaling_session.update_metadata.assert_called_once()
            call_kwargs = mock_journaling_session.update_metadata.call_args.kwargs

            metadata = call_kwargs["metadata"]
            # Validate it matches JournalContextMetadata structure
            journal_metadata = JournalContextMetadata(**metadata)
            assert journal_metadata.phase == "topic_selection"
            assert journal_metadata.generated_topics == []
            assert journal_metadata.selected_topic is None
            assert call_kwargs["chat_encryption_key"] == "test_key"
