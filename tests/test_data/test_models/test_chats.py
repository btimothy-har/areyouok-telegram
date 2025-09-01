"""Tests for Chats model."""

import hashlib
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from areyouok_telegram.data.models.chats import Chats


class TestChats:
    """Test Chats model."""

    def test_generate_chat_key(self):
        """Test chat key generation."""
        chat_id = "123456789"
        expected = hashlib.sha256(f"{chat_id}".encode()).hexdigest()
        assert Chats.generate_chat_key_hash(chat_id) == expected

    @pytest.mark.asyncio
    async def test_new_or_update_private_chat(self, mock_db_session, mock_telegram_chat):
        """Test inserting a private chat."""
        mock_result = AsyncMock()
        mock_db_session.execute.return_value = mock_result

        with patch.object(Chats, "get_by_id", return_value=None):
            await Chats.new_or_update(mock_db_session, chat=mock_telegram_chat)

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Get the statement that was executed
        call_args = mock_db_session.execute.call_args[0][0]

        # Verify it's an insert statement for chats table
        assert hasattr(call_args, "table")
        assert call_args.table.name == "chats"

    @pytest.mark.asyncio
    async def test_new_or_update_with_null_forum_status(self, mock_db_session, mock_telegram_chat):
        """Test handling chat with null is_forum status."""
        mock_telegram_chat.is_forum = None

        with patch.object(Chats, "get_by_id", return_value=None):
            await Chats.new_or_update(mock_db_session, chat=mock_telegram_chat)

        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_new_or_update_updates_existing(self, mock_db_session, mock_telegram_chat):
        """Test updating an existing chat."""
        # Create mock existing chat
        mock_existing_chat = AsyncMock()

        with patch.object(Chats, "get_by_id", return_value=mock_existing_chat):
            await Chats.new_or_update(mock_db_session, chat=mock_telegram_chat)

        # Verify execute was called
        mock_db_session.execute.assert_called_once()
