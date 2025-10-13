"""Tests for Chats model."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import InvalidToken

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

    def test_retrieve_key_when_encrypted_key_is_none(self):
        """Test retrieve_key returns None when encrypted_key is None."""
        # Create a chat instance with no encrypted key
        chat = Chats()
        chat.encrypted_key = None

        result = chat.retrieve_key()

        assert result is None

    def test_retrieve_key_when_encrypted_key_is_empty_string(self):
        """Test retrieve_key returns None when encrypted_key is empty string."""
        # Create a chat instance with empty encrypted key
        chat = Chats()
        chat.encrypted_key = ""

        result = chat.retrieve_key()

        assert result is None

    @patch("areyouok_telegram.data.models.chats.decrypt_chat_key")
    def test_retrieve_key_cache_hit(self, mock_decrypt):
        """Test retrieve_key returns cached key when available."""
        # Create a chat instance
        chat = Chats()
        chat.chat_key = "test_chat_key"
        chat.encrypted_key = "encrypted_test_key"

        # Pre-populate the cache
        expected_key = "decrypted_test_key"
        Chats._key_cache[chat.chat_key] = expected_key

        result = chat.retrieve_key()

        # Should return cached value without calling decrypt
        assert result == expected_key
        mock_decrypt.assert_not_called()

        # Clean up cache
        Chats._key_cache.clear()

    @patch("areyouok_telegram.data.models.chats.decrypt_chat_key")
    def test_retrieve_key_cache_miss(self, mock_decrypt):
        """Test retrieve_key decrypts and caches key when not in cache."""
        # Create a chat instance
        chat = Chats()
        chat.chat_key = "test_chat_key"
        chat.encrypted_key = "encrypted_test_key"

        # Ensure cache is empty
        Chats._key_cache.clear()

        # Mock the decrypt function
        expected_key = "decrypted_test_key"
        mock_decrypt.return_value = expected_key

        result = chat.retrieve_key()

        # Should decrypt the key
        mock_decrypt.assert_called_once_with("encrypted_test_key")
        # Should return the decrypted key
        assert result == expected_key
        # Should cache the decrypted key
        assert Chats._key_cache[chat.chat_key] == expected_key

        # Clean up cache
        Chats._key_cache.clear()

    @patch("areyouok_telegram.data.models.chats.decrypt_chat_key")
    def test_retrieve_key_decrypt_error_propagates(self, mock_decrypt):
        """Test retrieve_key propagates InvalidToken exception from decrypt."""
        # Create a chat instance
        chat = Chats()
        chat.chat_key = "test_chat_key"
        chat.encrypted_key = "corrupted_encrypted_key"

        # Ensure cache is empty
        Chats._key_cache.clear()

        # Mock decrypt to raise InvalidToken
        mock_decrypt.side_effect = InvalidToken("Invalid token")

        # Should propagate the exception
        with pytest.raises(InvalidToken):
            chat.retrieve_key()

        # Should have called decrypt
        mock_decrypt.assert_called_once_with("corrupted_encrypted_key")
        # Should not cache anything
        assert chat.chat_key not in Chats._key_cache

        # Clean up cache
        Chats._key_cache.clear()

    @pytest.mark.asyncio
    async def test_get_by_id_returns_chat_when_found(self, mock_db_session):
        """Test get_by_id returns chat when found in database."""
        chat_id = "123456789"

        # Create a mock result
        mock_chat = MagicMock(spec=Chats)
        mock_chat.chat_id = chat_id

        # Mock the scalars and first methods
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_chat

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db_session.execute.return_value = mock_result

        result = await Chats.get_by_id(mock_db_session, chat_id=chat_id)

        # Should execute a select statement
        mock_db_session.execute.assert_called_once()

        # Verify the statement is correct
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "whereclause")

        # Should return the found chat
        assert result == mock_chat

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_when_not_found(self, mock_db_session):
        """Test get_by_id returns None when chat is not found in database."""
        chat_id = "nonexistent_chat"

        # Mock the scalars and first methods to return None
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db_session.execute.return_value = mock_result

        result = await Chats.get_by_id(mock_db_session, chat_id=chat_id)

        # Should execute a select statement
        mock_db_session.execute.assert_called_once()

        # Verify the statement is correct
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "whereclause")

        # Should return None when not found
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_uses_correct_where_clause(self, mock_db_session):
        """Test get_by_id uses correct WHERE clause with chat_id."""
        chat_id = "test_chat_id_12345"

        # Mock the result chain
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db_session.execute.return_value = mock_result

        await Chats.get_by_id(mock_db_session, chat_id=chat_id)

        # Should execute exactly one statement
        mock_db_session.execute.assert_called_once()

        # Get the statement and verify it has the correct structure
        call_args = mock_db_session.execute.call_args[0][0]

        # Verify it's a select statement with a where clause
        assert hasattr(call_args, "whereclause")
        assert call_args.whereclause is not None
