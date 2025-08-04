"""Tests for the Users dataclass and its database operations."""

from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql import select

from areyouok_telegram.data.users import Users


@pytest.fixture
def mock_regular_user():
    """Create a mock telegram.User object for a regular user."""
    mock_user = MagicMock()
    mock_user.id = 123456789
    mock_user.is_bot = False
    mock_user.language_code = "en"
    mock_user.is_premium = False
    return mock_user


@pytest.fixture
def mock_premium_user():
    """Create a mock telegram.User object for a premium user."""
    mock_user = MagicMock()
    mock_user.id = 987654321
    mock_user.is_bot = False
    mock_user.language_code = "es"
    mock_user.is_premium = True
    return mock_user


@pytest.fixture
def mock_bot_user():
    """Create a mock telegram.User object for a bot."""
    mock_user = MagicMock()
    mock_user.id = 555666777
    mock_user.is_bot = True
    mock_user.language_code = None  # Bots often don't have language codes
    mock_user.is_premium = None  # Bots don't have premium status
    return mock_user


@pytest.fixture
def mock_user_no_language():
    """Create a mock telegram.User object with no language code."""
    mock_user = MagicMock()
    mock_user.id = 111222333
    mock_user.is_bot = False
    mock_user.language_code = None
    mock_user.is_premium = None  # Test None premium handling
    return mock_user


@pytest.fixture
def mock_user_different_language():
    """Create a mock telegram.User object with a different language."""
    mock_user = MagicMock()
    mock_user.id = 444555666
    mock_user.is_bot = False
    mock_user.language_code = "fr"
    mock_user.is_premium = False
    return mock_user


class TestUsersNewOrUpdate:
    """Test the new_or_update method of the Users class."""

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_new_regular_user(self, mock_async_database_session, mock_regular_user):
        """Test inserting a new regular user record."""
        # Call the method
        await Users.new_or_update(mock_async_database_session, mock_regular_user)

        # Verify the session.execute was called once
        mock_async_database_session.execute.assert_called_once()

        # Get the statement that was executed
        stmt = mock_async_database_session.execute.call_args[0][0]

        # Verify it's an insert statement
        assert isinstance(stmt, type(pg_insert(Users)))

        # Verify the values
        assert stmt.table.name == "users"

        values = stmt.compile().params
        assert values["user_id"] == "123456789"
        assert values["is_bot"] is False
        assert values["language_code"] == "en"
        assert values["is_premium"] is False
        assert values["created_at"] == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert values["updated_at"] == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_new_premium_user(self, mock_async_database_session, mock_premium_user):
        """Test inserting a new premium user record."""
        await Users.new_or_update(mock_async_database_session, mock_premium_user)

        mock_async_database_session.execute.assert_called_once()
        stmt = mock_async_database_session.execute.call_args[0][0]

        assert isinstance(stmt, type(pg_insert(Users)))
        assert stmt.table.name == "users"

        values = stmt.compile().params
        assert values["user_id"] == "987654321"
        assert values["is_bot"] is False
        assert values["language_code"] == "es"
        assert values["is_premium"] is True

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_new_bot_user(self, mock_async_database_session, mock_bot_user):
        """Test inserting a new bot user record."""
        await Users.new_or_update(mock_async_database_session, mock_bot_user)

        mock_async_database_session.execute.assert_called_once()
        stmt = mock_async_database_session.execute.call_args[0][0]

        assert isinstance(stmt, type(pg_insert(Users)))
        assert stmt.table.name == "users"

        values = stmt.compile().params
        assert values["user_id"] == "555666777"
        assert values["is_bot"] is True
        assert values["language_code"] is None
        assert values["is_premium"] is False  # Should default to False when None

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_user_no_language_none_premium(self, mock_async_database_session, mock_user_no_language):
        """Test inserting a user with None language and premium values."""
        await Users.new_or_update(mock_async_database_session, mock_user_no_language)

        mock_async_database_session.execute.assert_called_once()
        stmt = mock_async_database_session.execute.call_args[0][0]

        values = stmt.compile().params
        assert values["user_id"] == "111222333"
        assert values["is_bot"] is False
        assert values["language_code"] is None
        assert values["is_premium"] is False  # Should default to False when None

    async def test_on_conflict_do_update_configured(self, mock_async_database_session, mock_regular_user):
        """Test that the statement includes conflict resolution."""
        await Users.new_or_update(mock_async_database_session, mock_regular_user)

        stmt = mock_async_database_session.execute.call_args[0][0]

        # Verify that on_conflict was called by checking the statement has conflict handling
        assert hasattr(stmt, "_post_values_clause")
        assert stmt._post_values_clause is not None

    async def test_multiple_users_different_ids(self, mock_async_database_session):
        """Test inserting multiple users with different IDs."""

        # Create multiple mock users
        user1 = MagicMock()
        user1.id = 111
        user1.is_bot = False
        user1.language_code = "en"
        user1.is_premium = False

        user2 = MagicMock()
        user2.id = 222
        user2.is_bot = True
        user2.language_code = None
        user2.is_premium = None

        # Insert both users
        await Users.new_or_update(mock_async_database_session, user1)
        await Users.new_or_update(mock_async_database_session, user2)

        # Verify both inserts were executed
        assert mock_async_database_session.execute.call_count == 2

        # Verify different user IDs were used
        first_call_stmt = mock_async_database_session.execute.call_args_list[0][0][0]
        second_call_stmt = mock_async_database_session.execute.call_args_list[1][0][0]

        assert first_call_stmt.compile().params["user_id"] == "111"
        assert second_call_stmt.compile().params["user_id"] == "222"

    async def test_user_properties_mapping(self, mock_async_database_session, mock_user_different_language):
        """Test that all user properties are correctly mapped to database fields."""
        await Users.new_or_update(mock_async_database_session, mock_user_different_language)

        stmt = mock_async_database_session.execute.call_args[0][0]
        values = stmt.compile().params

        # Verify all telegram.User properties are correctly mapped
        assert values["user_id"] == str(mock_user_different_language.id)
        assert values["is_bot"] == mock_user_different_language.is_bot
        assert values["language_code"] == mock_user_different_language.language_code
        assert values["is_premium"] == mock_user_different_language.is_premium

    async def test_premium_status_none_handling(self, mock_async_database_session):
        """Test that None premium status is handled correctly."""
        user = MagicMock()
        user.id = 999888777
        user.is_bot = False
        user.language_code = "de"
        user.is_premium = None

        await Users.new_or_update(mock_async_database_session, user)

        stmt = mock_async_database_session.execute.call_args[0][0]
        values = stmt.compile().params

        # Premium should default to False when None
        assert values["is_premium"] is False

    async def test_premium_status_true_preserved(self, mock_async_database_session):
        """Test that True premium status is preserved."""
        user = MagicMock()
        user.id = 888777666
        user.is_bot = False
        user.language_code = "it"
        user.is_premium = True

        await Users.new_or_update(mock_async_database_session, user)

        stmt = mock_async_database_session.execute.call_args[0][0]
        values = stmt.compile().params

        # Premium should remain True
        assert values["is_premium"] is True

    async def test_premium_status_false_preserved(self, mock_async_database_session):
        """Test that False premium status is preserved."""
        user = MagicMock()
        user.id = 777666555
        user.is_bot = False
        user.language_code = "pt"
        user.is_premium = False

        await Users.new_or_update(mock_async_database_session, user)

        stmt = mock_async_database_session.execute.call_args[0][0]
        values = stmt.compile().params

        # Premium should remain False
        assert values["is_premium"] is False


class TestUsersGetById:
    """Test the get_by_id method of the Users class."""

    async def test_get_existing_user(self, mock_async_database_session):
        """Test retrieving an existing user by ID."""
        # Create a mock user object to return
        mock_user = MagicMock(spec=Users)
        mock_user.user_id = "123456789"
        mock_user.is_bot = False
        mock_user.language_code = "en"
        mock_user.is_premium = True
        mock_user.id = 1
        mock_user.created_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        mock_user.updated_at = datetime(2025, 1, 15, 15, 30, 0, tzinfo=UTC)

        # Configure the mock to return our user
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_user
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method
        result = await Users.get_by_id(mock_async_database_session, "123456789")

        # Verify the result
        assert result is mock_user
        assert result.user_id == "123456789"
        assert result.is_bot is False
        assert result.language_code == "en"
        assert result.is_premium is True

        # Verify the session.execute was called once
        mock_async_database_session.execute.assert_called_once()

        # Get the statement that was executed
        stmt = mock_async_database_session.execute.call_args[0][0]

        # Verify it's a select statement with correct table
        assert str(stmt.compile()) == str(select(Users).where(Users.user_id == "123456789").compile())

    async def test_get_non_existent_user(self, mock_async_database_session):
        """Test retrieving a non-existent user returns None."""
        # Configure the mock to return None
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method
        result = await Users.get_by_id(mock_async_database_session, "999999999")

        # Verify the result is None
        assert result is None

        # Verify the session.execute was called once
        mock_async_database_session.execute.assert_called_once()

    async def test_get_by_id_with_different_user_ids(self, mock_async_database_session):
        """Test that different user IDs generate different queries."""
        # Configure mock to return empty result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # First call
        await Users.get_by_id(mock_async_database_session, "111111111")
        first_stmt = mock_async_database_session.execute.call_args[0][0]

        # Reset mock
        mock_async_database_session.execute.reset_mock()

        # Second call with different ID
        await Users.get_by_id(mock_async_database_session, "222222222")
        second_stmt = mock_async_database_session.execute.call_args[0][0]

        # Verify different user IDs in the where clauses
        first_compiled = first_stmt.compile()
        second_compiled = second_stmt.compile()

        # Check the parameter values
        assert "111111111" in first_compiled.params.values()
        assert "222222222" in second_compiled.params.values()
        assert "111111111" not in second_compiled.params.values()
        assert "222222222" not in first_compiled.params.values()

    async def test_get_by_id_query_structure(self, mock_async_database_session):
        """Test the SQL query structure for get_by_id."""
        # Configure mock to return empty result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method
        await Users.get_by_id(mock_async_database_session, "987654321")

        # Get the statement that was executed
        stmt = mock_async_database_session.execute.call_args[0][0]

        # Compile the statement to inspect it
        compiled = stmt.compile()

        # Verify the query selects from the correct table
        assert Users.__table__ in compiled.statement.get_final_froms()

        # Verify the WHERE clause filters by user_id
        where_clause = compiled.statement.whereclause
        assert where_clause is not None

        # The WHERE clause should compare user_id column with the provided value
        assert "user_id" in str(where_clause)
        assert "987654321" in compiled.params.values()
