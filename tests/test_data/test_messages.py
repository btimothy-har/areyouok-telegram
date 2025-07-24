"""Tests for the Messages dataclass and its database operations."""

import hashlib
from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.messages import Messages


@pytest.fixture
def mock_text_message():
    """Create a mock telegram.Message object for a text message."""
    mock_message = MagicMock()
    mock_message.message_id = 12345
    mock_message.to_dict.return_value = {
        "message_id": 12345,
        "text": "Hello, world!",
        "date": 1705311000,
        "from": {"id": 987654321, "first_name": "John"},
    }
    return mock_message


@pytest.fixture
def mock_photo_message():
    """Create a mock telegram.Message object for a photo message."""
    mock_message = MagicMock()
    mock_message.message_id = 67890
    mock_message.to_dict.return_value = {
        "message_id": 67890,
        "photo": [{"file_id": "photo123", "width": 1280, "height": 720}],
        "caption": "A beautiful sunset",
        "date": 1705311200,
        "from": {"id": 555666777, "first_name": "Jane"},
    }
    return mock_message


@pytest.fixture
def mock_forwarded_message():
    """Create a mock telegram.Message object for a forwarded message."""
    mock_message = MagicMock()
    mock_message.message_id = 54321
    mock_message.to_dict.return_value = {
        "message_id": 54321,
        "text": "This is forwarded",
        "date": 1705311400,
        "forward_from": {"id": 111222333, "first_name": "Alice"},
        "from": {"id": 444555666, "first_name": "Bob"},
    }
    return mock_message


class TestMessagesGenerateMessageKey:
    """Test the generate_message_key static method."""

    def test_generate_key_basic_inputs(self):
        """Test key generation with basic string inputs."""
        user_id = "123456789"
        chat_id = "987654321"
        message_id = 12345

        key = Messages.generate_message_key(user_id, chat_id, message_id)

        # Verify it returns a SHA256 hash (64 hex characters)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

        # Verify it's deterministic
        key2 = Messages.generate_message_key(user_id, chat_id, message_id)
        assert key == key2

    def test_generate_key_different_inputs_different_keys(self):
        """Test that different inputs produce different keys."""
        key1 = Messages.generate_message_key("123", "456", 789)
        key2 = Messages.generate_message_key("123", "456", 790)
        key3 = Messages.generate_message_key("123", "457", 789)
        key4 = Messages.generate_message_key("124", "456", 789)

        # All keys should be different
        keys = [key1, key2, key3, key4]
        assert len(set(keys)) == 4

    def test_generate_key_matches_expected_hash(self):
        """Test that the generated key matches the expected SHA256 hash."""
        user_id = "100"
        chat_id = "200"
        message_id = 300

        expected_input = f"{user_id}:{chat_id}:{message_id}"
        expected_hash = hashlib.sha256(expected_input.encode()).hexdigest()

        actual_key = Messages.generate_message_key(user_id, chat_id, message_id)

        assert actual_key == expected_hash


class TestMessagesNewOrUpdate:
    """Test the new_or_update method of the Messages class."""

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_new_text_message(self, mock_async_database_session, mock_text_message):
        """Test inserting a new text message record."""
        user_id = "987654321"
        chat_id = "111222333"

        # Call the method
        await Messages.new_or_update(mock_async_database_session, user_id, chat_id, mock_text_message)

        # Verify the session.execute was called once
        mock_async_database_session.execute.assert_called_once()

        # Get the statement that was executed
        stmt = mock_async_database_session.execute.call_args[0][0]

        # Verify it's an insert statement
        assert isinstance(stmt, type(pg_insert(Messages)))

        # Verify the values
        assert stmt.table.name == "messages"

        values = stmt.compile().params
        expected_key = Messages.generate_message_key(user_id, chat_id, mock_text_message.message_id)

        assert values["message_key"] == expected_key
        assert values["message_id"] == "12345"
        assert values["user_id"] == "987654321"
        assert values["chat_id"] == "111222333"
        assert values["payload"] == mock_text_message.to_dict.return_value
        assert values["created_at"] == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert values["updated_at"] == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_new_photo_message(self, mock_async_database_session, mock_photo_message):
        """Test inserting a new photo message record."""
        user_id = "555666777"
        chat_id = "888999000"

        await Messages.new_or_update(mock_async_database_session, user_id, chat_id, mock_photo_message)

        mock_async_database_session.execute.assert_called_once()
        stmt = mock_async_database_session.execute.call_args[0][0]

        assert isinstance(stmt, type(pg_insert(Messages)))
        assert stmt.table.name == "messages"

        values = stmt.compile().params
        expected_key = Messages.generate_message_key(user_id, chat_id, mock_photo_message.message_id)

        assert values["message_key"] == expected_key
        assert values["message_id"] == "67890"
        assert values["user_id"] == "555666777"
        assert values["chat_id"] == "888999000"
        assert values["payload"] == mock_photo_message.to_dict.return_value

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_forwarded_message(self, mock_async_database_session, mock_forwarded_message):
        """Test inserting a forwarded message record."""
        user_id = "444555666"
        chat_id = "777888999"

        await Messages.new_or_update(mock_async_database_session, user_id, chat_id, mock_forwarded_message)

        mock_async_database_session.execute.assert_called_once()
        stmt = mock_async_database_session.execute.call_args[0][0]

        values = stmt.compile().params
        assert values["payload"] == mock_forwarded_message.to_dict.return_value

    async def test_on_conflict_do_update_configured(self, mock_async_database_session, mock_text_message):
        """Test that the statement includes conflict resolution."""
        user_id = "123456789"
        chat_id = "987654321"

        await Messages.new_or_update(mock_async_database_session, user_id, chat_id, mock_text_message)

        stmt = mock_async_database_session.execute.call_args[0][0]

        # Verify that on_conflict was called by checking the statement has conflict handling
        assert hasattr(stmt, "_post_values_clause")
        assert stmt._post_values_clause is not None

    async def test_multiple_messages_different_keys(self, mock_async_database_session):
        """Test inserting multiple messages with different keys."""

        # Create multiple mock messages
        message1 = MagicMock()
        message1.message_id = 111
        message1.to_dict.return_value = {"message_id": 111, "text": "Message 1"}

        message2 = MagicMock()
        message2.message_id = 222
        message2.to_dict.return_value = {"message_id": 222, "text": "Message 2"}

        # Insert both messages with different user/chat combinations
        await Messages.new_or_update(mock_async_database_session, "user1", "chat1", message1)
        await Messages.new_or_update(mock_async_database_session, "user2", "chat2", message2)

        # Verify both inserts were executed
        assert mock_async_database_session.execute.call_count == 2

        # Verify different message keys were used
        first_call_stmt = mock_async_database_session.execute.call_args_list[0][0][0]
        second_call_stmt = mock_async_database_session.execute.call_args_list[1][0][0]

        key1 = Messages.generate_message_key("user1", "chat1", 111)
        key2 = Messages.generate_message_key("user2", "chat2", 222)

        assert first_call_stmt.compile().params["message_key"] == key1
        assert second_call_stmt.compile().params["message_key"] == key2
        assert key1 != key2

    async def test_same_message_different_chats_different_keys(self, mock_async_database_session):
        """Test that the same message in different chats gets different keys."""
        message = MagicMock()
        message.message_id = 12345
        message.to_dict.return_value = {"message_id": 12345, "text": "Same message"}

        # Insert the same message in two different chats
        await Messages.new_or_update(mock_async_database_session, "user123", "chat1", message)
        await Messages.new_or_update(mock_async_database_session, "user123", "chat2", message)

        # Verify both inserts were executed
        assert mock_async_database_session.execute.call_count == 2

        # Verify different message keys were generated
        first_call_stmt = mock_async_database_session.execute.call_args_list[0][0][0]
        second_call_stmt = mock_async_database_session.execute.call_args_list[1][0][0]

        key1 = first_call_stmt.compile().params["message_key"]
        key2 = second_call_stmt.compile().params["message_key"]

        assert key1 != key2
