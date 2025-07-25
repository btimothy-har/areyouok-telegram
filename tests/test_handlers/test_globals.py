from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from areyouok_telegram.handlers import on_error_event
from areyouok_telegram.handlers import on_new_update


class TestGlobalUpdateHandler:
    """Test suite for global handlers functionality."""

    @pytest.mark.asyncio
    async def test_update_blank_update(
        self,
        mock_async_database_session,
        mock_update_empty,
    ):
        """Test on_new_update with the expected payload for a new private message."""

        mock_context = AsyncMock()

        with (
            patch("areyouok_telegram.data.Updates.new_or_upsert") as mock_updates_upsert,
            patch("areyouok_telegram.data.Users.new_or_update") as mock_users_update,
            patch("areyouok_telegram.data.Chats.new_or_update") as mock_chats_update,
        ):
            # Act
            await on_new_update(mock_update_empty, mock_context)
            mock_updates_upsert.assert_called_once_with(mock_async_database_session, update=mock_update_empty)
            mock_users_update.assert_not_called()
            mock_chats_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_with_user(self, mock_async_database_session, mock_update_empty, mock_user):
        """Test on_new_update with the expected payload for a new private message with user."""

        mock_context = AsyncMock()
        mock_update_empty.effective_user = mock_user

        with (
            patch("areyouok_telegram.data.Updates.new_or_upsert") as mock_updates_upsert,
            patch("areyouok_telegram.data.Users.new_or_update") as mock_users_update,
            patch("areyouok_telegram.data.Chats.new_or_update") as mock_chats_update,
        ):
            # Act
            await on_new_update(mock_update_empty, mock_context)

            mock_updates_upsert.assert_called_once_with(mock_async_database_session, update=mock_update_empty)
            mock_users_update.assert_called_once_with(
                session=mock_async_database_session, user=mock_update_empty.effective_user
            )
            mock_chats_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_with_chat(self, mock_async_database_session, mock_update_empty, mock_private_chat):
        """Test on_new_update with the expected payload for a new private message with user."""

        mock_context = AsyncMock()
        mock_update_empty.effective_chat = mock_private_chat

        with (
            patch("areyouok_telegram.data.Updates.new_or_upsert") as mock_updates_upsert,
            patch("areyouok_telegram.data.Users.new_or_update") as mock_users_update,
            patch("areyouok_telegram.data.Chats.new_or_update") as mock_chats_update,
            patch("areyouok_telegram.handlers.globals.schedule_conversation_job") as mock_schedule_job,
        ):
            # Act
            await on_new_update(mock_update_empty, mock_context)

            mock_updates_upsert.assert_called_once_with(mock_async_database_session, update=mock_update_empty)
            mock_users_update.assert_not_called()
            mock_chats_update.assert_called_once_with(
                session=mock_async_database_session, chat=mock_update_empty.effective_chat
            )
            mock_schedule_job.assert_called_once_with(
                context=mock_context, chat_id=str(mock_update_empty.effective_chat.id)
            )

    @pytest.mark.asyncio
    async def test_update_new_private_message(
        self,
        mock_async_database_session,
        mock_update_private_chat_new_message,
    ):
        """Test on_new_update with the expected payload for a new private message."""

        mock_context = AsyncMock()

        with (
            patch("areyouok_telegram.data.Updates.new_or_upsert") as mock_updates_upsert,
            patch("areyouok_telegram.data.Users.new_or_update") as mock_users_update,
            patch("areyouok_telegram.data.Chats.new_or_update") as mock_chats_update,
            patch("areyouok_telegram.handlers.globals.schedule_conversation_job") as mock_schedule_job,
        ):
            # Act
            await on_new_update(mock_update_private_chat_new_message, mock_context)

            mock_updates_upsert.assert_called_once_with(
                mock_async_database_session, update=mock_update_private_chat_new_message
            )
            mock_users_update.assert_called_once_with(
                session=mock_async_database_session, user=mock_update_private_chat_new_message.effective_user
            )
            mock_chats_update.assert_called_once_with(
                session=mock_async_database_session, chat=mock_update_private_chat_new_message.effective_chat
            )
            mock_schedule_job.assert_called_once_with(
                context=mock_context, chat_id=str(mock_update_private_chat_new_message.effective_chat.id)
            )


class TestGlobalErrorHandler:
    @pytest.mark.asyncio
    async def test_on_error_event_with_developer_chat_id(self):
        """Test on_error_event when DEVELOPER_CHAT_ID is configured."""
        mock_update = AsyncMock()
        mock_update.update_id = 12345

        mock_context = AsyncMock()
        mock_context.error = ValueError("Test error")
        mock_context.bot.send_message = AsyncMock()

        with patch("areyouok_telegram.handlers.globals.DEVELOPER_CHAT_ID", "123456789"):
            await on_error_event(mock_update, mock_context)

            mock_context.bot.send_message.assert_called_once()
            call_args = mock_context.bot.send_message.call_args
            assert call_args.kwargs["chat_id"] == "123456789"
            assert "An exception was raised while handling an update" in call_args.kwargs["text"]
            assert "ValueError: Test error" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_on_error_event_without_developer_chat_id(self):
        """Test on_error_event when DEVELOPER_CHAT_ID is not configured."""
        mock_update = AsyncMock()
        mock_update.update_id = 12345

        mock_context = AsyncMock()
        mock_context.error = ValueError("Test error")
        mock_context.bot.send_message = AsyncMock()

        with patch("areyouok_telegram.handlers.globals.DEVELOPER_CHAT_ID", None):
            await on_error_event(mock_update, mock_context)
            mock_context.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_error_event_with_none_update(self):
        """Test on_error_event when update is None."""
        mock_context = AsyncMock()
        mock_context.error = ValueError("Test error with no update")
        mock_context.bot.send_message = AsyncMock()

        with patch("areyouok_telegram.handlers.globals.DEVELOPER_CHAT_ID", "123456789"):
            with patch("areyouok_telegram.handlers.globals.logger") as mock_logger:
                await on_error_event(None, mock_context)

                # Should log error with different message
                mock_logger.error.assert_called_once_with(
                    "An error occurred but no update was provided.", exc_info=mock_context.error
                )

                # Should still send developer notification
                mock_context.bot.send_message.assert_called_once()
