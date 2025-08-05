"""Tests for the Updates dataclass and its database operations."""

import hashlib
from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.updates import Updates


@pytest.fixture
def mock_message_update():
    """Create a mock telegram.Update object for a message update."""
    mock_update = MagicMock()
    mock_update.update_id = 12345
    mock_update.to_json.return_value = '{"update_id": 12345, "message": {"message_id": 67890, "text": "Hello"}}'
    mock_update.to_dict.return_value = {
        "update_id": 12345,
        "message": {
            "message_id": 67890,
            "text": "Hello",
            "from": {"id": 123456789, "first_name": "John"},
            "chat": {"id": 987654321, "type": "private"},
            "date": 1705311000,
        },
    }
    return mock_update


@pytest.fixture
def mock_callback_query_update():
    """Create a mock telegram.Update object for a callback query update."""
    mock_update = MagicMock()
    mock_update.update_id = 54321
    mock_update.to_json.return_value = (
        '{"update_id": 54321, "callback_query": {"id": "callback123", "data": "button_pressed"}}'
    )
    mock_update.to_dict.return_value = {
        "update_id": 54321,
        "callback_query": {
            "id": "callback123",
            "data": "button_pressed",
            "from": {"id": 555666777, "first_name": "Jane"},
            "message": {
                "message_id": 11111,
                "chat": {"id": 888999000, "type": "private"},
            },
        },
    }
    return mock_update


@pytest.fixture
def mock_edited_message_update():
    """Create a mock telegram.Update object for an edited message update."""
    mock_update = MagicMock()
    mock_update.update_id = 98765
    mock_update.to_json.return_value = (
        '{"update_id": 98765, "edited_message": {"message_id": 22222, "text": "Edited text"}}'
    )
    mock_update.to_dict.return_value = {
        "update_id": 98765,
        "edited_message": {
            "message_id": 22222,
            "text": "Edited text",
            "edit_date": 1705311200,
            "from": {"id": 333444555, "first_name": "Alice"},
            "chat": {"id": 666777888, "type": "group", "title": "Test Group"},
        },
    }
    return mock_update


class TestUpdatesGenerateUpdateKey:
    """Test the generate_update_key static method."""

    def test_generate_key_basic_json(self):
        """Test key generation with basic JSON payload."""
        payload = '{"update_id": 123, "message": {"text": "hello"}}'

        key = Updates.generate_update_key(payload)

        # Verify it returns a SHA256 hash (64 hex characters)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

        # Verify it's deterministic
        key2 = Updates.generate_update_key(payload)
        assert key == key2

    def test_generate_key_different_payloads_different_keys(self):
        """Test that different payloads produce different keys."""
        payload1 = '{"update_id": 123, "message": {"text": "hello"}}'
        payload2 = '{"update_id": 124, "message": {"text": "hello"}}'
        payload3 = '{"update_id": 123, "message": {"text": "goodbye"}}'
        payload4 = '{"update_id": 123, "callback_query": {"data": "test"}}'

        key1 = Updates.generate_update_key(payload1)
        key2 = Updates.generate_update_key(payload2)
        key3 = Updates.generate_update_key(payload3)
        key4 = Updates.generate_update_key(payload4)

        # All keys should be different
        keys = [key1, key2, key3, key4]
        assert len(set(keys)) == 4

    def test_generate_key_matches_expected_hash(self):
        """Test that the generated key matches the expected SHA256 hash."""
        payload = '{"test": "data"}'

        expected_hash = hashlib.sha256(payload.encode()).hexdigest()
        actual_key = Updates.generate_update_key(payload)

        assert actual_key == expected_hash

    def test_generate_key_empty_payload(self):
        """Test key generation with empty payload."""
        payload = ""

        key = Updates.generate_update_key(payload)

        # Should still generate a valid hash
        assert len(key) == 64
        assert key == hashlib.sha256(b"").hexdigest()

    def test_generate_key_unicode_payload(self):
        """Test key generation with Unicode characters in payload."""
        payload = '{"message": {"text": "こんにちは🌍"}}'

        key = Updates.generate_update_key(payload)

        # Should handle Unicode properly
        assert len(key) == 64
        expected_hash = hashlib.sha256(payload.encode()).hexdigest()
        assert key == expected_hash


class TestUpdatesNewOrUpsert:
    """Test the new_or_upsert method of the Updates class."""

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_new_message_update(self, async_database_connection, mock_message_update):
        """Test inserting a new message update record."""
        # Call the method
        await Updates.new_or_upsert(async_database_connection, mock_message_update)

        # Verify the session.execute was called once
        async_database_connection.execute.assert_called_once()

        # Get the statement that was executed
        stmt = async_database_connection.execute.call_args[0][0]

        # Verify it's an insert statement
        assert isinstance(stmt, type(pg_insert(Updates)))

        # Verify the values
        assert stmt.table.name == "updates"

        values = stmt.compile().params
        expected_key = Updates.generate_update_key(mock_message_update.to_json.return_value)

        assert values["update_key"] == expected_key
        assert values["update_id"] == "12345"
        assert values["payload"] == mock_message_update.to_dict.return_value
        assert values["created_at"] == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert values["updated_at"] == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_new_callback_query_update(self, async_database_connection, mock_callback_query_update):
        """Test inserting a new callback query update record."""
        await Updates.new_or_upsert(async_database_connection, mock_callback_query_update)

        async_database_connection.execute.assert_called_once()
        stmt = async_database_connection.execute.call_args[0][0]

        assert isinstance(stmt, type(pg_insert(Updates)))
        assert stmt.table.name == "updates"

        values = stmt.compile().params
        expected_key = Updates.generate_update_key(mock_callback_query_update.to_json.return_value)

        assert values["update_key"] == expected_key
        assert values["update_id"] == "54321"
        assert values["payload"] == mock_callback_query_update.to_dict.return_value

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_edited_message_update(self, async_database_connection, mock_edited_message_update):
        """Test inserting an edited message update record."""
        await Updates.new_or_upsert(async_database_connection, mock_edited_message_update)

        async_database_connection.execute.assert_called_once()
        stmt = async_database_connection.execute.call_args[0][0]

        values = stmt.compile().params
        assert values["update_id"] == "98765"
        assert values["payload"] == mock_edited_message_update.to_dict.return_value

    async def test_on_conflict_do_update_configured(self, async_database_connection, mock_message_update):
        """Test that the statement includes conflict resolution."""
        await Updates.new_or_upsert(async_database_connection, mock_message_update)

        stmt = async_database_connection.execute.call_args[0][0]

        # Verify that on_conflict was called by checking the statement has conflict handling
        assert hasattr(stmt, "_post_values_clause")
        assert stmt._post_values_clause is not None

    async def test_update_key_generation_called(self, async_database_connection, mock_message_update):
        """Test that the update key is generated from the JSON payload."""
        await Updates.new_or_upsert(async_database_connection, mock_message_update)

        # Verify to_json was called for key generation
        mock_message_update.to_json.assert_called_once()

        # Verify to_dict was called for payload storage
        mock_message_update.to_dict.assert_called_once()

        stmt = async_database_connection.execute.call_args[0][0]
        values = stmt.compile().params

        expected_key = Updates.generate_update_key(mock_message_update.to_json.return_value)
        assert values["update_key"] == expected_key

    async def test_multiple_updates_different_keys(self, async_database_connection):
        """Test inserting multiple updates with different keys."""

        # Create multiple mock updates
        update1 = MagicMock()
        update1.update_id = 111
        update1.to_json.return_value = '{"update_id": 111, "message": {"text": "first"}}'
        update1.to_dict.return_value = {"update_id": 111, "message": {"text": "first"}}

        update2 = MagicMock()
        update2.update_id = 222
        update2.to_json.return_value = '{"update_id": 222, "message": {"text": "second"}}'
        update2.to_dict.return_value = {"update_id": 222, "message": {"text": "second"}}

        # Insert both updates
        await Updates.new_or_upsert(async_database_connection, update1)
        await Updates.new_or_upsert(async_database_connection, update2)

        # Verify both inserts were executed
        assert async_database_connection.execute.call_count == 2

        # Verify different update keys were used
        first_call_stmt = async_database_connection.execute.call_args_list[0][0][0]
        second_call_stmt = async_database_connection.execute.call_args_list[1][0][0]

        key1 = Updates.generate_update_key(update1.to_json.return_value)
        key2 = Updates.generate_update_key(update2.to_json.return_value)

        assert first_call_stmt.compile().params["update_key"] == key1
        assert second_call_stmt.compile().params["update_key"] == key2
        assert key1 != key2

    async def test_same_update_id_different_content_different_keys(self, async_database_connection):
        """Test that updates with same ID but different content get different keys."""
        # Create two updates with same update_id but different content
        update1 = MagicMock()
        update1.update_id = 12345
        update1.to_json.return_value = '{"update_id": 12345, "message": {"text": "original"}}'
        update1.to_dict.return_value = {"update_id": 12345, "message": {"text": "original"}}

        update2 = MagicMock()
        update2.update_id = 12345  # Same ID
        update2.to_json.return_value = '{"update_id": 12345, "message": {"text": "modified"}}'
        update2.to_dict.return_value = {"update_id": 12345, "message": {"text": "modified"}}

        # Insert both updates
        await Updates.new_or_upsert(async_database_connection, update1)
        await Updates.new_or_upsert(async_database_connection, update2)

        # Verify both inserts were executed
        assert async_database_connection.execute.call_count == 2

        # Verify different update keys were generated despite same update_id
        first_call_stmt = async_database_connection.execute.call_args_list[0][0][0]
        second_call_stmt = async_database_connection.execute.call_args_list[1][0][0]

        key1 = first_call_stmt.compile().params["update_key"]
        key2 = second_call_stmt.compile().params["update_key"]

        assert key1 != key2
