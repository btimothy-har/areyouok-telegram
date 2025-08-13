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

        # Mock get_by_id to return the user object after upsert
        with patch.object(Users, "get_by_id", return_value=mock_user):
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

        # Mock get_by_id to return the user object after upsert
        with patch.object(Users, "get_by_id", return_value=mock_user):
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
