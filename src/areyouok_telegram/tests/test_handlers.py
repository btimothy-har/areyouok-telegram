from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from areyouok_telegram.handlers.globals import on_new_update


class TestGlobalHandlers:
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
        ):
            # Act
            await on_new_update(mock_update_empty, mock_context)
            mock_updates_upsert.assert_called_once_with(mock_async_database_session, update=mock_update_empty)

    @pytest.mark.asyncio
    async def test_update_with_user(self, mock_async_database_session, mock_update_empty, mock_user):
        """Test on_new_update with the expected payload for a new private message with user."""

        mock_context = AsyncMock()
        mock_update_empty.effective_user = mock_user

        with (
            patch("areyouok_telegram.data.Updates.new_or_upsert") as mock_updates_upsert,
            patch("areyouok_telegram.data.Users.new_or_update") as mock_users_update,
        ):
            # Act
            await on_new_update(mock_update_empty, mock_context)

            mock_updates_upsert.assert_called_once_with(mock_async_database_session, update=mock_update_empty)
            mock_users_update.assert_called_once_with(
                session=mock_async_database_session, user=mock_update_empty.effective_user
            )

    @pytest.mark.asyncio
    async def test_update_with_chat(self, mock_async_database_session, mock_update_empty, mock_private_chat):
        """Test on_new_update with the expected payload for a new private message with user."""

        mock_context = AsyncMock()
        mock_update_empty.effective_chat = mock_private_chat

        with (
            patch("areyouok_telegram.data.Updates.new_or_upsert") as mock_updates_upsert,
            patch("areyouok_telegram.data.Chats.new_or_update") as mock_chats_update,
        ):
            # Act
            await on_new_update(mock_update_empty, mock_context)

            mock_updates_upsert.assert_called_once_with(mock_async_database_session, update=mock_update_empty)
            mock_chats_update.assert_called_once_with(
                session=mock_async_database_session, chat=mock_update_empty.effective_chat
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
