"""Tests for handlers/messages.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.handlers.exceptions import NoEditedMessageError, NoMessageError, NoMessageReactionError
from areyouok_telegram.handlers.messages import on_edit_message, on_message_react, on_new_message


class TestOnNewMessage:
    """Test the on_new_message handler."""

    @pytest.mark.asyncio
    async def test_on_new_message_handles_message_successfully(self, frozen_time, mock_telegram_user):
        """Test successful handling of new message."""
        # Create mock update with message
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message = MagicMock(spec=telegram.Message)
        mock_update.message.date = frozen_time
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()
        mock_context.bot.id = 123456

        # Create mock active session
        mock_active_session = MagicMock()

        with (
            patch(
                "areyouok_telegram.handlers.messages.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ) as mock_get_session,
            patch(
                "areyouok_telegram.handlers.messages.data_operations.new_session_event", new=AsyncMock()
            ) as mock_new_event,
            patch("areyouok_telegram.handlers.messages.telegram_call", new=AsyncMock()) as mock_telegram_call,
            patch("areyouok_telegram.handlers.messages.generate_feedback_context", new=AsyncMock()) as _,
            patch("asyncio.create_task") as mock_create_task,
            patch("random.random", return_value=0.2),  # Mock to be < 1/3 to trigger task creation
        ):
            await on_new_message(mock_update, mock_context)

            # Verify session was retrieved/created
            mock_get_session.assert_called_once_with(
                chat_id=str(mock_update.effective_chat.id),
                timestamp=mock_update.message.date,
            )

            # Verify typing action was sent
            mock_telegram_call.assert_called_once_with(
                mock_context.bot.send_chat_action,
                chat_id=mock_update.effective_chat.id,
                action=telegram.constants.ChatAction.TYPING,
            )

            # Verify session event was recorded
            mock_new_event.assert_called_once_with(
                session=mock_active_session,
                message=mock_update.message,
                user_id=str(mock_telegram_user.id),
                is_user=True,
            )

            # Verify feedback context generation task was created
            mock_create_task.assert_called_once()
            # The task should be a coroutine for generate_feedback_context

            # Clean up the coroutine and AsyncMock to prevent warnings
            task_coro = mock_create_task.call_args[0][0]
            task_coro.close()

    @pytest.mark.asyncio
    async def test_on_new_message_without_message_raises_error(self):
        """Test that handler raises NoMessageError when update has no message."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message = None

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with pytest.raises(NoMessageError) as exc_info:
            await on_new_message(mock_update, mock_context)

        assert exc_info.value.update_id == 123
        assert "Expected to receive a new message in update: 123" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_on_new_message_creates_feedback_context_task(self, frozen_time, mock_telegram_user):
        """Test that new message handler creates async task for feedback context generation."""
        # Create mock update with message
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 456
        mock_update.message = MagicMock(spec=telegram.Message)
        mock_update.message.date = frozen_time
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 999

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()
        mock_context.bot.id = "bot_789"

        mock_active_session = MagicMock()
        mock_active_session.session_id = "session_123"

        with (
            patch(
                "areyouok_telegram.handlers.messages.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ),
            patch("areyouok_telegram.handlers.messages.data_operations.new_session_event", new=AsyncMock()),
            patch("areyouok_telegram.handlers.messages.telegram_call", new=AsyncMock()),
            patch("asyncio.create_task") as mock_create_task,
            patch("random.random", return_value=0.2),  # Mock to be < 1/3 to trigger task creation
        ):
            await on_new_message(mock_update, mock_context)

            # Verify task creation was called
            mock_create_task.assert_called_once()

            # Get the coroutine that was passed to create_task
            task_coro = mock_create_task.call_args[0][0]

            # The task should be for generate_feedback_context with correct parameters
            # This is an indirect test since we can't easily inspect the coroutine parameters
            assert task_coro is not None

            # Close the coroutine to prevent warnings
            task_coro.close()

    @pytest.mark.asyncio
    async def test_on_new_message_feedback_task_doesnt_block_main_flow(self, frozen_time, mock_telegram_user):
        """Test that feedback context generation doesn't block main message processing."""
        # Create mock update with message
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 789
        mock_update.message = MagicMock(spec=telegram.Message)
        mock_update.message.date = frozen_time
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 111

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()
        mock_context.bot.id = "bot_222"

        mock_active_session = MagicMock()

        # Mock a slow generate_feedback_context function
        async def slow_generate_feedback_context(*_, **__):
            await asyncio.sleep(0.1)  # Simulate slow operation
            return "feedback context"

        with (
            patch(
                "areyouok_telegram.handlers.messages.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ),
            patch(
                "areyouok_telegram.handlers.messages.data_operations.new_session_event", new=AsyncMock()
            ) as mock_new_event,
            patch("areyouok_telegram.handlers.messages.telegram_call", new=AsyncMock()) as mock_telegram_call,
            patch(
                "areyouok_telegram.handlers.messages.generate_feedback_context",
                new=AsyncMock(side_effect=slow_generate_feedback_context),
            ),
            patch("random.random", return_value=0.2),  # Mock to be < 1/3 to trigger task creation
        ):
            # This should complete quickly despite the slow feedback context generation
            await on_new_message(mock_update, mock_context)

            # Verify main flow operations completed (not blocked by feedback task)
            mock_telegram_call.assert_called_once()
            mock_new_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_new_message_skips_feedback_context_task_when_random_high(self, frozen_time, mock_telegram_user):
        """Test that feedback context task is not created when random value >= 1/3."""
        # Create mock update with message
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 999
        mock_update.message = MagicMock(spec=telegram.Message)
        mock_update.message.date = frozen_time
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 888

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()
        mock_context.bot.id = "bot_888"

        mock_active_session = MagicMock()

        with (
            patch(
                "areyouok_telegram.handlers.messages.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ),
            patch(
                "areyouok_telegram.handlers.messages.data_operations.new_session_event", new=AsyncMock()
            ) as mock_new_event,
            patch("areyouok_telegram.handlers.messages.telegram_call", new=AsyncMock()) as mock_telegram_call,
            patch("asyncio.create_task") as mock_create_task,
            patch("random.random", return_value=0.5),  # Mock to be >= 1/3 to skip task creation
        ):
            await on_new_message(mock_update, mock_context)

            # Verify main flow operations completed
            mock_telegram_call.assert_called_once()
            mock_new_event.assert_called_once()

            # Verify task creation was NOT called
            mock_create_task.assert_not_called()


class TestOnEditMessage:
    """Test the on_edit_message handler."""

    @pytest.mark.asyncio
    async def test_on_edit_message_handles_edited_message_successfully(self, mock_telegram_user):
        """Test successful handling of edited message."""
        # Create mock update with edited message
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.edited_message = MagicMock(spec=telegram.Message)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789
        mock_update.message = MagicMock(spec=telegram.Message)

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock active session
        mock_active_session = MagicMock()

        with (
            patch(
                "areyouok_telegram.handlers.messages.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ) as mock_get_session,
            patch(
                "areyouok_telegram.handlers.messages.data_operations.new_session_event", new=AsyncMock()
            ) as mock_new_event,
        ):
            await on_edit_message(mock_update, mock_context)

            # Verify session was retrieved/created
            mock_get_session.assert_called_once_with(
                chat_id=str(mock_update.effective_chat.id),
                timestamp=mock_update.edited_message.date,
            )

            # Verify session event was recorded
            mock_new_event.assert_called_once_with(
                session=mock_active_session,
                message=mock_update.edited_message,
                user_id=str(mock_telegram_user.id),
                is_user=True,
            )

    @pytest.mark.asyncio
    async def test_on_edit_message_without_edited_message_raises_error(self):
        """Test that handler raises NoEditedMessageError when update has no edited message."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.edited_message = None

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with pytest.raises(NoEditedMessageError) as exc_info:
            await on_edit_message(mock_update, mock_context)

        assert exc_info.value.update_id == 123
        assert "Expected to receive an edited message in update: 123" in str(exc_info.value)


class TestOnMessageReact:
    """Test the on_message_react handler."""

    @pytest.mark.asyncio
    async def test_on_message_react_handles_reaction_successfully(self, mock_telegram_user):
        """Test successful handling of message reaction."""
        # Create mock update with message reaction
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.id = 789
        mock_update.message = MagicMock(spec=telegram.Message)

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock active session
        mock_active_session = MagicMock()

        with (
            patch(
                "areyouok_telegram.handlers.messages.data_operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_active_session),
            ) as mock_get_session,
            patch(
                "areyouok_telegram.handlers.messages.data_operations.new_session_event", new=AsyncMock()
            ) as mock_new_event,
        ):
            await on_message_react(mock_update, mock_context)

            # Verify session was retrieved/created
            mock_get_session.assert_called_once_with(
                chat_id=str(mock_update.effective_chat.id),
                timestamp=mock_update.message_reaction.date,
            )

            # Verify session event was recorded
            mock_new_event.assert_called_once_with(
                session=mock_active_session,
                message=mock_update.message_reaction,
                user_id=str(mock_telegram_user.id),
                is_user=True,
            )

    @pytest.mark.asyncio
    async def test_on_message_react_without_reaction_raises_error(self):
        """Test that handler raises NoMessageReactionError when update has no message reaction."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.update_id = 123
        mock_update.message_reaction = None

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with pytest.raises(NoMessageReactionError) as exc_info:
            await on_message_react(mock_update, mock_context)

        assert exc_info.value.update_id == 123
        assert "Expected to receive a message reaction in update: 123" in str(exc_info.value)
