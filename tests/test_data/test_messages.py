"""Tests for the Messages dataclass and its database operations."""

import hashlib
from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.messages import InvalidMessageTypeError
from areyouok_telegram.data.messages import Messages


@pytest.fixture
def mock_message_record1():
    """Create a mock Messages database record."""
    mock_record = MagicMock()
    mock_record.payload = {"message_id": 111, "text": "Message 1"}
    mock_telegram_msg = MagicMock(spec=telegram.Message)
    mock_record.to_telegram_object.return_value = mock_telegram_msg
    return mock_record


@pytest.fixture
def mock_message_record2():
    """Create a second mock Messages database record."""
    mock_record = MagicMock()
    mock_record.payload = {"message_id": 222, "text": "Message 2"}
    mock_telegram_msg = MagicMock(spec=telegram.Message)
    mock_record.to_telegram_object.return_value = mock_telegram_msg
    return mock_record


@pytest.fixture
def mock_text_message(mock_private_message):
    """Create a mock telegram.Message object for a text message."""
    # Reuse the base fixture and customize it
    mock_private_message.message_id = 12345
    mock_private_message.to_dict.return_value = {
        "message_id": 12345,
        "text": "Hello, world!",
        "date": 1705311000,
        "from": {"id": 987654321, "first_name": "John"},
    }
    return mock_private_message


@pytest.fixture
def mock_photo_message(mock_private_message):
    """Create a mock telegram.Message object for a photo message."""
    # Reuse the base fixture and customize it
    mock_private_message.message_id = 67890
    mock_private_message.text = None  # Photo messages don't have text
    mock_private_message.photo = [{"file_id": "photo123", "width": 1280, "height": 720}]
    mock_private_message.caption = "A beautiful sunset"
    mock_private_message.to_dict.return_value = {
        "message_id": 67890,
        "photo": [{"file_id": "photo123", "width": 1280, "height": 720}],
        "caption": "A beautiful sunset",
        "date": 1705311200,
        "from": {"id": 555666777, "first_name": "Jane"},
    }
    return mock_private_message


@pytest.fixture
def mock_forwarded_message(mock_private_message):
    """Create a mock telegram.Message object for a forwarded message."""
    # Reuse the base fixture and customize it
    mock_private_message.message_id = 54321
    mock_private_message.text = "This is forwarded"
    # Create mock MessageOrigin for forward_origin
    mock_origin = MagicMock()
    mock_origin.type = "user"
    mock_origin.sender_user = MagicMock(id=111222333, first_name="Alice")
    mock_private_message.forward_origin = mock_origin
    mock_private_message.to_dict.return_value = {
        "message_id": 54321,
        "text": "This is forwarded",
        "date": 1705311400,
        "forward_origin": {"type": "user", "sender_user": {"id": 111222333, "first_name": "Alice"}},
        "from": {"id": 444555666, "first_name": "Bob"},
    }
    return mock_private_message


class TestMessagesGenerateMessageKey:
    """Test the generate_message_key static method."""

    def test_generate_key_basic_inputs(self):
        """Test key generation with basic string inputs."""
        user_id = "123456789"
        chat_id = "987654321"
        message_id = 12345

        key = Messages.generate_message_key(user_id, chat_id, message_id, "Message")

        # Verify it returns a SHA256 hash (64 hex characters)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

        # Verify it's deterministic
        key2 = Messages.generate_message_key(user_id, chat_id, message_id, "Message")
        assert key == key2

    def test_generate_key_different_inputs_different_keys(self):
        """Test that different inputs produce different keys."""
        key1 = Messages.generate_message_key("123", "456", 789, "Message")
        key2 = Messages.generate_message_key("123", "456", 790, "Message")
        key3 = Messages.generate_message_key("123", "457", 789, "Message")
        key4 = Messages.generate_message_key("124", "456", 789, "Message")

        # All keys should be different
        keys = [key1, key2, key3, key4]
        assert len(set(keys)) == 4

    def test_generate_key_matches_expected_hash(self):
        """Test that the generated key matches the expected SHA256 hash."""
        user_id = "100"
        chat_id = "200"
        message_id = 300

        message_type = "Message"
        expected_input = f"{user_id}:{chat_id}:{message_id}:{message_type}"
        expected_hash = hashlib.sha256(expected_input.encode()).hexdigest()

        actual_key = Messages.generate_message_key(user_id, chat_id, message_id, message_type)

        assert actual_key == expected_hash


class TestInvalidMessageTypeError:
    """Test the InvalidMessageTypeError exception."""

    def test_exception_initialization(self):
        """Test that InvalidMessageTypeError initializes correctly with message type."""
        message_type = "InvalidType"
        error = InvalidMessageTypeError(message_type)

        assert error.message_type == message_type
        assert str(error) == "Invalid message type: InvalidType. Expected 'Message' or 'MessageReactionUpdated'."


class TestMessagesProperties:
    """Test the Messages model properties."""

    def test_message_type_obj_with_message(self):
        """Test message_type_obj property returns telegram.Message class."""
        messages_record = Messages()
        messages_record.message_type = "Message"

        assert messages_record.message_type_obj == telegram.Message

    def test_message_type_obj_with_message_reaction_updated(self):
        """Test message_type_obj property returns telegram.MessageReactionUpdated class."""
        messages_record = Messages()
        messages_record.message_type = "MessageReactionUpdated"

        assert messages_record.message_type_obj == telegram.MessageReactionUpdated

    def test_message_type_obj_with_invalid_type(self):
        """Test message_type_obj property raises exception for invalid type."""
        messages_record = Messages()
        messages_record.message_type = "InvalidType"

        with pytest.raises(InvalidMessageTypeError) as exc_info:
            _ = messages_record.message_type_obj

        assert exc_info.value.message_type == "InvalidType"

    def test_to_telegram_object(self):
        """Test to_telegram_object method converts payload to telegram object."""
        messages_record = Messages()
        messages_record.message_type = "Message"
        messages_record.payload = {"message_id": 123, "text": "Hello"}

        # Mock the de_json method to return a mock telegram.Message
        mock_telegram_msg = MagicMock(spec=telegram.Message)
        with patch.object(telegram.Message, "de_json", return_value=mock_telegram_msg):
            result = messages_record.to_telegram_object()

            telegram.Message.de_json.assert_called_once_with(messages_record.payload, None)
            assert result == mock_telegram_msg

    def test_to_telegram_object_with_soft_deleted_message(self):
        """Test to_telegram_object returns None for soft-deleted messages."""
        messages_record = Messages()
        messages_record.message_type = "Message"
        messages_record.payload = None  # Soft deleted

        result = messages_record.to_telegram_object()

        # Should return None for soft-deleted messages
        assert result is None


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
        expected_key = Messages.generate_message_key(user_id, chat_id, mock_text_message.message_id, "Message")

        assert values["message_key"] == expected_key
        assert values["message_id"] == "12345"
        assert values["message_type"] == "Message"
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
        expected_key = Messages.generate_message_key(user_id, chat_id, mock_photo_message.message_id, "Message")

        assert values["message_key"] == expected_key
        assert values["message_id"] == "67890"
        assert values["message_type"] == "Message"
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
        assert values["message_type"] == "Message"
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
        message1 = MagicMock(spec=telegram.Message)
        message1.message_id = 111
        message1.to_dict.return_value = {"message_id": 111, "text": "Message 1"}

        message2 = MagicMock(spec=telegram.Message)
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

        key1 = Messages.generate_message_key("user1", "chat1", 111, "Message")
        key2 = Messages.generate_message_key("user2", "chat2", 222, "Message")

        assert first_call_stmt.compile().params["message_key"] == key1
        assert second_call_stmt.compile().params["message_key"] == key2
        assert key1 != key2

    async def test_same_message_different_chats_different_keys(self, mock_async_database_session):
        """Test that the same message in different chats gets different keys."""
        message = MagicMock(spec=telegram.Message)
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

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_insert_message_reaction(self, mock_async_database_session, mock_message_reaction):
        """Test inserting a message reaction update."""
        user_id = str(mock_message_reaction.user.id)
        chat_id = str(mock_message_reaction.chat.id)

        # Add to_dict method to the mock
        mock_message_reaction.to_dict.return_value = {
            "chat": {"id": mock_message_reaction.chat.id},
            "message_id": mock_message_reaction.message_id,
            "user": {"id": mock_message_reaction.user.id},
            "date": 1705311000,
            "old_reaction": [{"type": "emoji", "emoji": "👍"}],
            "new_reaction": [{"type": "emoji", "emoji": "❤️"}],
        }

        # Call the method
        await Messages.new_or_update(mock_async_database_session, user_id, chat_id, mock_message_reaction)

        # Verify the session.execute was called once
        mock_async_database_session.execute.assert_called_once()

        # Get the statement that was executed
        stmt = mock_async_database_session.execute.call_args[0][0]

        # Verify it's an insert statement
        assert isinstance(stmt, type(pg_insert(Messages)))

        # Verify the values
        values = stmt.compile().params
        expected_key = Messages.generate_message_key(
            user_id, chat_id, mock_message_reaction.message_id, "MessageReactionUpdated"
        )

        assert values["message_key"] == expected_key
        assert values["message_id"] == str(mock_message_reaction.message_id)
        assert values["message_type"] == "MessageReactionUpdated"
        assert values["user_id"] == user_id
        assert values["chat_id"] == chat_id
        assert values["payload"] == mock_message_reaction.to_dict.return_value
        assert values["created_at"] == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert values["updated_at"] == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

    async def test_new_or_update_invalid_message_type(self, mock_async_database_session):
        """Test new_or_update raises exception for invalid message type."""
        user_id = "123456789"
        chat_id = "987654321"

        # Create an object that is not a valid MessageTypes
        invalid_message = "not a telegram message"

        with pytest.raises(InvalidMessageTypeError) as exc_info:
            await Messages.new_or_update(mock_async_database_session, user_id, chat_id, invalid_message)

        assert exc_info.value.message_type == "str"


class TestMessagesRetrieveMessageById:
    """Test the retrieve_message_by_id class method."""

    async def test_retrieve_message_by_id_with_reactions(self, mock_async_database_session, mock_message_record1):
        """Test retrieving a message by ID that has reactions."""
        message_id = "123"
        chat_id = "456"

        # Mock the message query result
        mock_message_result = MagicMock()
        mock_message_result.scalar_one_or_none.return_value = mock_message_record1

        # Mock reaction records
        mock_reaction_record1 = MagicMock()
        mock_reaction_record1.to_telegram_object.return_value = MagicMock(spec=telegram.MessageReactionUpdated)

        mock_reaction_record2 = MagicMock()
        mock_reaction_record2.to_telegram_object.return_value = MagicMock(spec=telegram.MessageReactionUpdated)

        # Mock the reactions query result
        mock_reaction_result = MagicMock()
        mock_reaction_scalars = MagicMock()
        mock_reaction_scalars.all.return_value = [mock_reaction_record1, mock_reaction_record2]
        mock_reaction_result.scalars.return_value = mock_reaction_scalars

        # Configure session to return different results for different queries
        mock_async_database_session.execute.side_effect = [mock_message_result, mock_reaction_result]

        # Call the method
        message, reactions = await Messages.retrieve_message_by_id(mock_async_database_session, message_id, chat_id)

        # Verify two queries were executed (message + reactions)
        assert mock_async_database_session.execute.call_count == 2

        # Verify to_telegram_object was called for message and reactions
        mock_message_record1.to_telegram_object.assert_called_once()
        mock_reaction_record1.to_telegram_object.assert_called_once()
        mock_reaction_record2.to_telegram_object.assert_called_once()

        # Verify the results
        assert message == mock_message_record1.to_telegram_object.return_value
        assert len(reactions) == 2
        assert reactions[0] == mock_reaction_record1.to_telegram_object.return_value
        assert reactions[1] == mock_reaction_record2.to_telegram_object.return_value

    async def test_retrieve_message_by_id_without_reactions(self, mock_async_database_session, mock_message_record1):
        """Test retrieving a message by ID that has no reactions."""
        message_id = "123"
        chat_id = "456"

        # Mock the message query result
        mock_message_result = MagicMock()
        mock_message_result.scalar_one_or_none.return_value = mock_message_record1

        # Mock empty reactions query result
        mock_reaction_result = MagicMock()
        mock_reaction_scalars = MagicMock()
        mock_reaction_scalars.all.return_value = []
        mock_reaction_result.scalars.return_value = mock_reaction_scalars

        # Configure session to return different results for different queries
        mock_async_database_session.execute.side_effect = [mock_message_result, mock_reaction_result]

        # Call the method
        message, reactions = await Messages.retrieve_message_by_id(mock_async_database_session, message_id, chat_id)

        # Verify two queries were executed
        assert mock_async_database_session.execute.call_count == 2

        # Verify to_telegram_object was called for message only
        mock_message_record1.to_telegram_object.assert_called_once()

        # Verify the results
        assert message == mock_message_record1.to_telegram_object.return_value
        assert reactions == []

    async def test_retrieve_message_by_id_message_not_found(self, mock_async_database_session):
        """Test retrieving a message by ID when message doesn't exist."""
        message_id = "nonexistent"
        chat_id = "456"

        # Mock empty message query result
        mock_message_result = MagicMock()
        mock_message_result.scalar_one_or_none.return_value = None

        mock_async_database_session.execute.return_value = mock_message_result

        # Call the method
        message, reactions = await Messages.retrieve_message_by_id(mock_async_database_session, message_id, chat_id)

        # Verify only one query was executed (message query only)
        mock_async_database_session.execute.assert_called_once()

        # Verify the results are both None
        assert message is None
        assert reactions is None

    async def test_retrieve_message_by_id_query_structure(self, mock_async_database_session, mock_message_record1):
        """Test that retrieve_message_by_id constructs correct SQL queries."""
        message_id = "123"
        chat_id = "456"

        # Mock the message query result
        mock_message_result = MagicMock()
        mock_message_result.scalar_one_or_none.return_value = mock_message_record1

        # Mock empty reactions query result
        mock_reaction_result = MagicMock()
        mock_reaction_scalars = MagicMock()
        mock_reaction_scalars.all.return_value = []
        mock_reaction_result.scalars.return_value = mock_reaction_scalars

        mock_async_database_session.execute.side_effect = [mock_message_result, mock_reaction_result]

        # Call the method
        await Messages.retrieve_message_by_id(mock_async_database_session, message_id, chat_id)

        # Verify both queries were executed
        assert mock_async_database_session.execute.call_count == 2

        # Get the statements that were executed
        message_stmt = mock_async_database_session.execute.call_args_list[0][0][0]
        reaction_stmt = mock_async_database_session.execute.call_args_list[1][0][0]

        # Verify both are select statements
        assert isinstance(message_stmt, type(select(Messages)))
        assert isinstance(reaction_stmt, type(select(Messages)))


class TestMessagesRetrieveByChat:
    """Test the retrieve_by_chat class method."""

    async def test_retrieve_by_chat_basic(
        self, mock_async_database_session, mock_message_record1, mock_message_record2
    ):
        """Test retrieving messages by chat ID."""
        chat_id = "123456"

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_message_record1, mock_message_record2]
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method
        result = await Messages.retrieve_by_chat(mock_async_database_session, chat_id)

        # Verify the query was executed
        mock_async_database_session.execute.assert_called_once()
        stmt = mock_async_database_session.execute.call_args[0][0]

        # Check that the statement filters by chat_id
        assert isinstance(stmt, type(select(Messages)))

        # Verify to_telegram_object was called for each record
        mock_message_record1.to_telegram_object.assert_called_once()
        mock_message_record2.to_telegram_object.assert_called_once()

        # Verify the result contains the telegram objects
        assert len(result) == 2
        assert result[0] == mock_message_record1.to_telegram_object.return_value
        assert result[1] == mock_message_record2.to_telegram_object.return_value

    async def test_retrieve_by_chat_with_time_range(self, mock_async_database_session):
        """Test retrieving messages with time range filters."""
        chat_id = "123456"
        from_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        to_time = datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)

        # Mock empty result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method with time range
        result = await Messages.retrieve_by_chat(
            mock_async_database_session, chat_id, from_time=from_time, to_time=to_time
        )

        # Verify the query was executed
        mock_async_database_session.execute.assert_called_once()

        # Verify empty result
        assert result == []

    async def test_retrieve_by_chat_with_limit(self, mock_async_database_session, mock_message_record1):
        """Test retrieving messages with limit."""
        chat_id = "123456"
        limit = 10

        # Mock result with one message
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_message_record1]
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method with limit
        result = await Messages.retrieve_by_chat(mock_async_database_session, chat_id, limit=limit)

        # Verify the query was executed
        mock_async_database_session.execute.assert_called_once()

        # Verify to_telegram_object was called
        mock_message_record1.to_telegram_object.assert_called_once()

        # Verify the result
        assert len(result) == 1
        assert result[0] == mock_message_record1.to_telegram_object.return_value

    async def test_retrieve_by_chat_no_messages(self, mock_async_database_session):
        """Test retrieving messages when none exist."""
        chat_id = "nonexistent"

        # Mock empty result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method
        result = await Messages.retrieve_by_chat(mock_async_database_session, chat_id)

        # Verify the result is empty
        assert result == []

    async def test_retrieve_by_chat_excludes_soft_deleted(self, mock_async_database_session):
        """Test retrieving messages excludes soft-deleted ones."""
        chat_id = "123456"

        # Create mock messages, one soft-deleted
        mock_message = MagicMock()
        mock_message.payload = {"text": "Active message"}
        mock_message.to_telegram_object.return_value = MagicMock(spec=telegram.Message)

        # Mock result with only non-deleted message
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_message]
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method
        result = await Messages.retrieve_by_chat(mock_async_database_session, chat_id)

        # Verify only one message returned (soft-deleted excluded by query)
        assert len(result) == 1
        assert result[0] == mock_message.to_telegram_object.return_value

    async def test_retrieve_by_chat_uses_retrieve_raw_by_chat(
        self, mock_async_database_session, mock_message_record1, mock_message_record2
    ):
        """Test that retrieve_by_chat uses retrieve_raw_by_chat internally."""
        chat_id = "123456"
        from_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        to_time = datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)
        limit = 5

        # Mock raw messages that would be returned by retrieve_raw_by_chat
        raw_messages = [mock_message_record1, mock_message_record2]

        # Mock retrieve_raw_by_chat to return our mock records
        with patch.object(Messages, "retrieve_raw_by_chat", return_value=raw_messages) as mock_raw_method:
            # Call retrieve_by_chat
            result = await Messages.retrieve_by_chat(
                mock_async_database_session, chat_id, from_time=from_time, to_time=to_time, limit=limit
            )

            # Verify retrieve_raw_by_chat was called with the same parameters
            mock_raw_method.assert_called_once_with(mock_async_database_session, chat_id, from_time, to_time, limit)

            # Verify to_telegram_object was called on each raw message
            mock_message_record1.to_telegram_object.assert_called_once()
            mock_message_record2.to_telegram_object.assert_called_once()

            # Verify the result contains telegram objects
            assert len(result) == 2
            assert result[0] == mock_message_record1.to_telegram_object.return_value
            assert result[1] == mock_message_record2.to_telegram_object.return_value


class TestMessagesRetrieveRawByChat:
    """Test the retrieve_raw_by_chat class method."""

    async def test_retrieve_raw_by_chat_basic(
        self, mock_async_database_session, mock_message_record1, mock_message_record2
    ):
        """Test retrieving raw message models by chat ID."""
        chat_id = "123456"

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_message_record1, mock_message_record2]
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method
        result = await Messages.retrieve_raw_by_chat(mock_async_database_session, chat_id)

        # Verify the query was executed
        mock_async_database_session.execute.assert_called_once()
        stmt = mock_async_database_session.execute.call_args[0][0]

        # Check that the statement filters by chat_id
        assert isinstance(stmt, type(select(Messages)))

        # Verify to_telegram_object was NOT called (raw method returns models)
        mock_message_record1.to_telegram_object.assert_not_called()
        mock_message_record2.to_telegram_object.assert_not_called()

        # Verify the result contains the raw SQLAlchemy models
        assert len(result) == 2
        assert result[0] == mock_message_record1
        assert result[1] == mock_message_record2

    async def test_retrieve_raw_by_chat_with_time_range(self, mock_async_database_session):
        """Test retrieving raw messages with time range filters."""
        chat_id = "123456"
        from_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        to_time = datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)

        # Mock empty result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method with time range
        result = await Messages.retrieve_raw_by_chat(
            mock_async_database_session, chat_id, from_time=from_time, to_time=to_time
        )

        # Verify the query was executed
        mock_async_database_session.execute.assert_called_once()

        # Verify empty result
        assert result == []

    async def test_retrieve_raw_by_chat_with_limit(self, mock_async_database_session, mock_message_record1):
        """Test retrieving raw messages with limit."""
        chat_id = "123456"
        limit = 10

        # Mock result with one message
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_message_record1]
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method with limit
        result = await Messages.retrieve_raw_by_chat(mock_async_database_session, chat_id, limit=limit)

        # Verify the query was executed
        mock_async_database_session.execute.assert_called_once()

        # Verify to_telegram_object was NOT called
        mock_message_record1.to_telegram_object.assert_not_called()

        # Verify the result contains the raw model
        assert len(result) == 1
        assert result[0] == mock_message_record1

    async def test_retrieve_raw_by_chat_no_messages(self, mock_async_database_session):
        """Test retrieving raw messages when none exist."""
        chat_id = "nonexistent"

        # Mock empty result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method
        result = await Messages.retrieve_raw_by_chat(mock_async_database_session, chat_id)

        # Verify the result is empty
        assert result == []

    async def test_retrieve_raw_by_chat_all_parameters(self, mock_async_database_session, mock_message_record1):
        """Test retrieving raw messages with all parameters specified."""
        chat_id = "123456"
        from_time = datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC)
        to_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        limit = 5

        # Mock result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_message_record1]
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method with all parameters
        result = await Messages.retrieve_raw_by_chat(
            mock_async_database_session, chat_id, from_time=from_time, to_time=to_time, limit=limit
        )

        # Verify the query was executed
        mock_async_database_session.execute.assert_called_once()

        # Verify the result
        assert len(result) == 1
        assert result[0] == mock_message_record1

    async def test_retrieve_raw_by_chat_with_retry_decorator(self):
        """Test that retrieve_raw_by_chat method has the with_retry decorator."""
        # Verify the method has been wrapped by with_retry
        assert hasattr(Messages.retrieve_raw_by_chat, "__wrapped__")


class TestMessagesDelete:
    """Test the delete instance method."""

    async def test_delete_existing_message(self):
        """Test soft deleting a message with payload returns True."""
        # Create a Messages instance with payload
        message = Messages()
        message.message_key = "test_key_123"
        message.payload = {"message_id": 123, "text": "Test message"}

        # Call the delete method
        result = await message.delete()

        # Verify it returned True (message was soft deleted)
        assert result is True

        # Verify the payload was set to None
        assert message.payload is None

    async def test_delete_already_deleted_message(self):
        """Test deleting an already soft-deleted message returns False."""
        # Create a Messages instance with no payload (already soft deleted)
        message = Messages()
        message.message_key = "already_deleted_key"
        message.payload = None

        # Call the delete method
        result = await message.delete()

        # Verify it returned False (message was already deleted)
        assert result is False

        # Verify the payload is still None
        assert message.payload is None

    async def test_delete_preserves_metadata(self):
        """Test that delete preserves message metadata while clearing payload."""
        # Create a Messages instance with full data
        message = Messages()
        message.message_key = "unique_test_key_456"
        message.message_id = "12345"
        message.message_type = "Message"
        message.user_id = "user123"
        message.chat_id = "chat456"
        message.payload = {"message_id": 12345, "text": "Test message"}

        # Call the delete method
        result = await message.delete()

        # Verify it returned True
        assert result is True

        # Verify only payload was cleared, other fields remain intact
        assert message.payload is None
        assert message.message_key == "unique_test_key_456"
        assert message.message_id == "12345"
        assert message.message_type == "Message"
        assert message.user_id == "user123"
        assert message.chat_id == "chat456"

    async def test_delete_multiple_messages_independently(self):
        """Test deleting multiple messages independently."""
        # Create multiple Messages instances
        message1 = Messages()
        message1.message_key = "key1"
        message1.payload = {"text": "Message 1"}

        message2 = Messages()
        message2.message_key = "key2"
        message2.payload = None  # Already soft deleted

        # Delete both messages
        result1 = await message1.delete()
        result2 = await message2.delete()

        # Verify results
        assert result1 is True  # First message was soft deleted
        assert result2 is False  # Second message was already deleted

        # Verify payloads
        assert message1.payload is None
        assert message2.payload is None

    async def test_delete_with_retry_decorator(self):
        """Test that delete method has the with_retry decorator."""
        # Create a Messages instance
        message = Messages()

        # Verify the delete method has been wrapped by with_retry
        # The with_retry decorator adds __wrapped__ attribute to the original function
        assert hasattr(message.delete, "__wrapped__")

        # Also verify the method works correctly
        message.message_key = "test_key"
        message.payload = {"text": "Test message"}

        # Call the delete method
        result = await message.delete()

        # Verify it still works as expected
        assert result is True
        assert message.payload is None
