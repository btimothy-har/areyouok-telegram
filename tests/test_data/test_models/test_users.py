"""Tests for Users model."""

import hashlib
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram

from areyouok_telegram.data.models.users import Users


class TestUsers:
    """Test Users model."""

    def test_generate_user_key(self):
        """Test user key generation."""
        user_id = "123456789"
        expected = hashlib.sha256(f"{user_id}".encode()).hexdigest()
        assert Users.generate_user_key(user_id) == expected

    @pytest.mark.asyncio
    async def test_new_or_update_new_user(self, mock_db_session, mock_telegram_user):
        """Test inserting a new user."""
        # Setup mock execute to simulate insert
        mock_result = AsyncMock()
        mock_db_session.execute.return_value = mock_result

        # Create mock user to be returned
        mock_user = AsyncMock(spec=Users)
        mock_user.user_id = str(mock_telegram_user.id)

        # Mock get_by_id to return None first (new user), then the user object
        with patch.object(Users, "get_by_id", side_effect=[None, mock_user]):
            result = await Users.new_or_update(mock_db_session, mock_telegram_user)

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify user object is returned
        assert result == mock_user

        # Get the statement that was executed
        call_args = mock_db_session.execute.call_args[0][0]

        # Verify it's an insert statement with correct values
        assert hasattr(call_args, "table")
        assert call_args.table.name == "users"

    @pytest.mark.asyncio
    async def test_new_or_update_existing_user(self, mock_db_session, mock_telegram_user):
        """Test updating an existing user with conflict resolution."""
        mock_result = AsyncMock()
        mock_db_session.execute.return_value = mock_result

        # Update user attributes
        mock_telegram_user.is_premium = False
        mock_telegram_user.language_code = "es"

        # Mock get_by_id to return an existing user both times
        mock_existing_user = MagicMock(spec=Users)
        mock_existing_user.user_id = str(mock_telegram_user.id)
        with patch.object(Users, "get_by_id", return_value=mock_existing_user):
            result = await Users.new_or_update(mock_db_session, mock_telegram_user)

        # Verify execute was called with upsert
        mock_db_session.execute.assert_called_once()

        # Verify user object is returned
        assert result == mock_existing_user

    @pytest.mark.asyncio
    async def test_new_or_update_no_premium_status(self, mock_db_session):
        """Test handling user without premium status."""
        user = MagicMock(spec=telegram.User)
        user.id = 987654321
        user.is_bot = True
        user.language_code = "fr"
        user.is_premium = None  # No premium status
        user.username = None  # No username

        # Create mock user to be returned
        mock_user = AsyncMock(spec=Users)
        mock_user.user_id = str(user.id)

        # Mock get_by_id to return None first (new user), then the user object
        with patch.object(Users, "get_by_id", side_effect=[None, mock_user]):
            result = await Users.new_or_update(mock_db_session, user)

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify user object is returned
        assert result == mock_user

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, mock_db_session):
        """Test retrieving a user by ID when found."""
        # Create mock user result
        mock_user = MagicMock(spec=Users)
        mock_user.user_id = "123456789"

        # Setup mock chain for execute().scalars().first()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_user
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Users.get_by_id(mock_db_session, "123456789")

        assert result == mock_user
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, mock_db_session):
        """Test retrieving a user by ID when not found."""
        # Setup mock chain for execute().scalars().first() returning None
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Users.get_by_id(mock_db_session, "nonexistent")

        assert result is None
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.users.generate_user_key")
    @patch("areyouok_telegram.data.models.users.encrypt_user_key")
    async def test_new_user_with_username_generates_encrypted_key(
        self, mock_encrypt, mock_generate, mock_db_session, mock_telegram_user
    ):
        """Test that new user with username gets an encrypted key."""
        # Setup mocks
        mock_telegram_user.username = "testuser"
        mock_generate.return_value = "test_key"
        mock_encrypt.return_value = "encrypted_key"

        # Create mock user to be returned
        mock_user = AsyncMock(spec=Users)
        mock_user.user_id = str(mock_telegram_user.id)

        # Mock get_by_id to return None first (new user), then the user object
        with patch.object(Users, "get_by_id", side_effect=[None, mock_user]):
            result = await Users.new_or_update(mock_db_session, mock_telegram_user)

        # Verify key generation and encryption were called
        mock_generate.assert_called_once()
        mock_encrypt.assert_called_once_with("test_key", "testuser")

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify user object is returned
        assert result == mock_user

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.users.generate_user_key")
    @patch("areyouok_telegram.data.models.users.encrypt_user_key")
    async def test_new_user_without_username_no_key_generated(
        self, mock_encrypt, mock_generate, mock_db_session, mock_telegram_user
    ):
        """Test that new user without username doesn't get a key."""
        # Setup mocks
        mock_telegram_user.username = None

        # Create mock user to be returned
        mock_user = AsyncMock(spec=Users)
        mock_user.user_id = str(mock_telegram_user.id)

        # Mock get_by_id to return None first (new user), then the user object
        with patch.object(Users, "get_by_id", side_effect=[None, mock_user]):
            result = await Users.new_or_update(mock_db_session, mock_telegram_user)

        # Verify key generation and encryption were NOT called
        mock_generate.assert_not_called()
        mock_encrypt.assert_not_called()

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify user object is returned
        assert result == mock_user

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.users.generate_user_key")
    @patch("areyouok_telegram.data.models.users.encrypt_user_key")
    async def test_existing_user_no_key_generated(
        self, mock_encrypt, mock_generate, mock_db_session, mock_telegram_user
    ):
        """Test that existing user doesn't get a new key."""
        # Setup mocks
        mock_telegram_user.username = "existinguser"
        mock_existing_user = MagicMock(spec=Users)
        mock_existing_user.user_id = str(mock_telegram_user.id)

        # Mock get_by_id to return an existing user both times
        with patch.object(Users, "get_by_id", return_value=mock_existing_user):
            result = await Users.new_or_update(mock_db_session, mock_telegram_user)

        # Verify key generation and encryption were NOT called
        mock_generate.assert_not_called()
        mock_encrypt.assert_not_called()

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify user object is returned
        assert result == mock_existing_user

    def test_retrieve_key_no_encrypted_key(self):
        """Test retrieve_key returns None when no encrypted key is stored."""
        user = Users()
        user.user_id = "123"
        user.user_key = "user_key_123"
        user.encrypted_key = None

        result = user.retrieve_key("testuser")
        assert result is None

    @patch("areyouok_telegram.data.models.users.decrypt_user_key")
    def test_retrieve_key_decrypts_and_caches(self, mock_decrypt):
        """Test retrieve_key decrypts key and caches the result."""
        # Clear the cache before test
        Users._key_cache.clear()

        # Setup
        user = Users()
        user.user_id = "123"
        user.user_key = "user_key_123"
        user.encrypted_key = "encrypted_key_data"
        username = "testuser"
        decrypted_key = "decrypted_fernet_key"
        mock_decrypt.return_value = decrypted_key

        # First call - should decrypt
        result1 = user.retrieve_key(username)
        assert result1 == decrypted_key
        mock_decrypt.assert_called_once_with("encrypted_key_data", username)

        # Second call - should use cache
        mock_decrypt.reset_mock()
        result2 = user.retrieve_key(username)
        assert result2 == decrypted_key
        mock_decrypt.assert_not_called()  # Should not decrypt again

    @patch("areyouok_telegram.data.models.users.decrypt_user_key")
    def test_retrieve_key_cache_different_users(self, mock_decrypt):
        """Test that cache is properly keyed by user_key."""
        # Clear the cache before test
        Users._key_cache.clear()

        # Setup different users
        user1 = Users()
        user1.user_id = "123"
        user1.user_key = "user_key_123"
        user1.encrypted_key = "encrypted_key_1"

        user2 = Users()
        user2.user_id = "456"
        user2.user_key = "user_key_456"
        user2.encrypted_key = "encrypted_key_2"

        username = "testuser"
        mock_decrypt.side_effect = ["decrypted_key_1", "decrypted_key_2"]

        # Call retrieve_key on both users
        result1 = user1.retrieve_key(username)
        result2 = user2.retrieve_key(username)

        # Both should have been decrypted (different cache keys)
        assert result1 == "decrypted_key_1"
        assert result2 == "decrypted_key_2"
        assert mock_decrypt.call_count == 2
