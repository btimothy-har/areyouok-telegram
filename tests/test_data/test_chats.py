"""Tests for the Chats dataclass and its database operations."""

from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.chats import Chats


@pytest.fixture
def mock_forum_chat_with_title():
    """Create a mock telegram.Chat object for a forum with a title."""
    mock_chat = MagicMock()
    mock_chat.id = 987654321
    mock_chat.type = "supergroup"
    mock_chat.title = "Tech Forum"
    mock_chat.is_forum = True
    return mock_chat


@pytest.fixture
def mock_group_chat_no_forum():
    """Create a mock telegram.Chat object for a group that's not a forum."""
    mock_chat = MagicMock()
    mock_chat.id = 111222333
    mock_chat.type = "group"
    mock_chat.title = "Friends Group"
    mock_chat.is_forum = False
    return mock_chat


@pytest.fixture
def mock_private_chat_no_title():
    """Create a mock telegram.Chat object for a private chat with no title."""
    mock_chat = MagicMock()
    mock_chat.id = 555666777
    mock_chat.type = "private"
    mock_chat.title = None
    mock_chat.is_forum = None
    return mock_chat


class TestChatsNewOrUpdate:
    """Test the new_or_update method of the Chats class."""

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_new_forum_chat(self, mock_async_database_session, mock_forum_chat_with_title):
        """Test inserting a new forum chat record."""
        # Call the method
        await Chats.new_or_update(mock_async_database_session, mock_forum_chat_with_title)

        # Verify the session.execute was called once
        mock_async_database_session.execute.assert_called_once()

        # Get the statement that was executed
        stmt = mock_async_database_session.execute.call_args[0][0]

        # Verify it's an insert statement
        assert isinstance(stmt, type(pg_insert(Chats)))

        # Verify the values
        assert stmt.table.name == "chats"

        values = stmt.compile().params
        assert values["chat_id"] == "987654321"
        assert values["type"] == "supergroup"
        assert values["title"] == "Tech Forum"
        assert values["is_forum"] is True
        assert values["created_at"] == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert values["updated_at"] == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_new_group_chat(self, mock_async_database_session, mock_group_chat_no_forum):
        """Test inserting a new group chat that's not a forum."""
        await Chats.new_or_update(mock_async_database_session, mock_group_chat_no_forum)

        mock_async_database_session.execute.assert_called_once()
        stmt = mock_async_database_session.execute.call_args[0][0]

        assert isinstance(stmt, type(pg_insert(Chats)))
        assert stmt.table.name == "chats"

        values = stmt.compile().params
        assert values["chat_id"] == "111222333"
        assert values["type"] == "group"
        assert values["title"] == "Friends Group"
        assert values["is_forum"] is False

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_private_chat_with_none_values(self, mock_async_database_session, mock_private_chat_no_title):
        """Test inserting a private chat with None values for title and is_forum."""
        await Chats.new_or_update(mock_async_database_session, mock_private_chat_no_title)

        mock_async_database_session.execute.assert_called_once()
        stmt = mock_async_database_session.execute.call_args[0][0]

        assert isinstance(stmt, type(pg_insert(Chats)))
        assert stmt.table.name == "chats"

        values = stmt.compile().params

        assert values["chat_id"] == "555666777"
        assert values["type"] == "private"
        assert values["title"] is None
        assert values["is_forum"] is False  # Should default to False when None

    async def test_on_conflict_do_update_configured(self, mock_async_database_session, mock_forum_chat_with_title):
        """Test that the statement includes conflict resolution."""
        await Chats.new_or_update(mock_async_database_session, mock_forum_chat_with_title)

        stmt = mock_async_database_session.execute.call_args[0][0]

        # Simply verify that on_conflict was called by checking the statement has conflict handling
        assert hasattr(stmt, "_post_values_clause")
        assert stmt._post_values_clause is not None

    async def test_multiple_chats_different_ids(self, mock_async_database_session):
        """Test inserting multiple chats with different IDs."""

        # Create multiple mock chats
        chat1 = MagicMock()
        chat1.id = 111
        chat1.type = "private"
        chat1.title = None
        chat1.is_forum = None

        chat2 = MagicMock()
        chat2.id = 222
        chat2.type = "group"
        chat2.title = "Test Group"
        chat2.is_forum = False

        # Insert both chats
        await Chats.new_or_update(mock_async_database_session, chat1)
        await Chats.new_or_update(mock_async_database_session, chat2)

        # Verify both inserts were executed
        assert mock_async_database_session.execute.call_count == 2

        # Verify different chat IDs were used
        first_call_stmt = mock_async_database_session.execute.call_args_list[0][0][0]
        second_call_stmt = mock_async_database_session.execute.call_args_list[1][0][0]

        assert first_call_stmt.compile().params["chat_id"] == "111"
        assert second_call_stmt.compile().params["chat_id"] == "222"
