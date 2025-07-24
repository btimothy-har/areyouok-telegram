"""Tests for the Sessions dataclass and its database operations."""

import hashlib
from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from sqlalchemy import select

from areyouok_telegram.data.sessions import InvalidMessageTypeError
from areyouok_telegram.data.sessions import Sessions


class TestSessionsGenerateSessionKey:
    """Test the generate_session_key static method."""

    def test_generate_key_basic_inputs(self):
        """Test key generation with basic inputs."""
        chat_id = "123456789"
        session_start = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        key = Sessions.generate_session_key(chat_id, session_start)

        # Verify it returns a SHA256 hash (64 hex characters)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

        # Verify it's deterministic
        key2 = Sessions.generate_session_key(chat_id, session_start)
        assert key == key2

    def test_generate_key_different_inputs_different_keys(self):
        """Test that different inputs produce different keys."""
        timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        timestamp2 = datetime(2025, 1, 15, 10, 31, 0, tzinfo=UTC)

        key1 = Sessions.generate_session_key("123", timestamp)
        key2 = Sessions.generate_session_key("124", timestamp)
        key3 = Sessions.generate_session_key("123", timestamp2)

        # All keys should be different
        keys = [key1, key2, key3]
        assert len(set(keys)) == 3

    def test_generate_key_matches_expected_hash(self):
        """Test that the generated key matches the expected SHA256 hash."""
        chat_id = "100"
        session_start = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        expected_input = f"{chat_id}:{session_start.isoformat()}"
        expected_hash = hashlib.sha256(expected_input.encode()).hexdigest()

        actual_key = Sessions.generate_session_key(chat_id, session_start)

        assert actual_key == expected_hash


class TestSessionsGetActiveSession:
    """Test the get_active_session class method."""

    async def test_get_active_session_exists(self, mock_async_database_session):
        """Test retrieving an active session that exists."""
        chat_id = "123456"

        # Create a mock active session
        mock_session = MagicMock(spec=Sessions)
        mock_session.chat_id = chat_id
        mock_session.session_end = None

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_async_database_session.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_active_session(mock_async_database_session, chat_id)

        # Verify the result
        assert result == mock_session

        # Verify the query
        mock_async_database_session.execute.assert_called_once()
        stmt = mock_async_database_session.execute.call_args[0][0]

        # Check that the statement has correct filters
        assert isinstance(stmt, type(select(Sessions)))

    async def test_get_active_session_none(self, mock_async_database_session):
        """Test retrieving an active session when none exists."""
        chat_id = "123456"

        # Mock no result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_database_session.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_active_session(mock_async_database_session, chat_id)

        # Verify no session was found
        assert result is None


class TestSessionsGetInactiveSessions:
    """Test the get_inactive_sessions class method."""

    async def test_get_inactive_sessions(self, mock_async_database_session):
        """Test retrieving inactive sessions."""
        cutoff_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Create mock inactive sessions
        session1 = MagicMock(spec=Sessions)
        session1.last_user_activity = datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC)
        session1.session_end = None

        session2 = MagicMock(spec=Sessions)
        session2.last_user_activity = datetime(2025, 1, 15, 8, 0, 0, tzinfo=UTC)
        session2.session_end = None

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [session1, session2]
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_inactive_sessions(mock_async_database_session, cutoff_time)

        # Verify the result
        assert len(result) == 2
        assert session1 in result
        assert session2 in result

        # Verify the query was executed
        mock_async_database_session.execute.assert_called_once()

    async def test_get_inactive_sessions_empty(self, mock_async_database_session):
        """Test retrieving inactive sessions when none exist."""
        cutoff_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Mock no results
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_async_database_session.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_inactive_sessions(mock_async_database_session, cutoff_time)

        # Verify empty result
        assert result == []


class TestSessionsCreateSession:
    """Test the create_session class method."""

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_create_session(self, mock_async_database_session):
        """Test creating a new session."""
        chat_id = "123456789"
        timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Call the method
        result = await Sessions.create_session(mock_async_database_session, chat_id, timestamp)

        # Verify the session was added
        mock_async_database_session.add.assert_called_once()

        # Get the session object that was added
        added_session = mock_async_database_session.add.call_args[0][0]

        # Verify the session attributes
        assert isinstance(added_session, Sessions)
        assert added_session.chat_id == chat_id
        assert added_session.session_start == timestamp
        assert added_session.last_user_message is None  # Should be None initially
        assert added_session.last_user_activity is None  # Should be None initially
        assert added_session.session_key == Sessions.generate_session_key(chat_id, timestamp)
        assert added_session.session_end is None
        assert added_session.message_count is None

        # Verify the returned object is the same
        assert result == added_session


class TestSessionsNewMessage:
    """Test the new_message method."""

    async def test_new_message_user_first_message(self):
        """Test recording first user message."""
        # Create a session instance
        session = Sessions()
        session.last_user_activity = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.message_count = None

        new_timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Record user message
        await session.new_message(new_timestamp, "user")

        # Verify updates
        assert session.last_user_message == new_timestamp
        assert session.last_user_activity == new_timestamp
        assert session.message_count == 1
        assert session.last_bot_message is None

    async def test_new_message_user_increment_count(self):
        """Test recording user message with existing message count."""
        # Create a session instance with existing message count
        session = Sessions()
        session.last_user_activity = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.message_count = 5

        new_timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Record user message
        await session.new_message(new_timestamp, "user")

        # Verify updates
        assert session.last_user_message == new_timestamp
        assert session.last_user_activity == new_timestamp
        assert session.message_count == 6

    async def test_new_message_bot(self):
        """Test recording bot message doesn't increment user count."""
        # Create a session instance
        session = Sessions()
        session.last_user_activity = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.last_user_message = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.message_count = 3

        new_timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Record bot message
        await session.new_message(new_timestamp, "bot")

        # Verify updates
        assert session.last_bot_message == new_timestamp
        assert session.last_user_activity == new_timestamp
        assert session.message_count == 3  # Should not increment for bot messages
        assert session.last_user_message == datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)  # Unchanged

    async def test_new_message_invalid_type(self):
        """Test that invalid message_type raises InvalidMessageTypeError."""
        session = Sessions()
        new_timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        with pytest.raises(InvalidMessageTypeError, match="Invalid message_type: invalid. Must be 'user' or 'bot'."):
            await session.new_message(new_timestamp, "invalid")  # type: ignore


class TestSessionsNewUserActivity:
    """Test the new_user_activity method."""

    async def test_new_user_activity_no_count_increment(self):
        """Test recording user activity without incrementing message count."""
        # Create a session instance
        session = Sessions()
        session.last_user_activity = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.message_count = 5

        new_timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Record user activity (like edit)
        await session.new_user_activity(new_timestamp)

        # Verify only activity timestamp updated
        assert session.last_user_activity == new_timestamp
        assert session.message_count == 5  # Should remain unchanged


class TestSessionsCloseSession:
    """Test the close_session method."""

    @freeze_time("2025-01-15 11:00:00", tz_offset=0)
    async def test_close_session(self, mock_async_database_session):
        """Test closing a session."""
        # Create a session instance
        session = Sessions()
        session.chat_id = "123456"
        session.session_start = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.session_end = None

        # Mock the get_messages method
        mock_messages = [MagicMock() for _ in range(10)]
        with patch.object(session, "get_messages", return_value=mock_messages):
            # Close the session
            await session.close_session(mock_async_database_session)

        # Verify the session was closed
        assert session.session_end == datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)
        assert session.message_count == 10


class TestSessionsGetMessages:
    """Test the get_messages method."""

    async def test_get_messages_active_session(self, mock_async_database_session):
        """Test retrieving messages from an active session."""
        # Create a session instance
        session = Sessions()
        session.chat_id = "123456"
        session.session_start = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.session_end = None  # Active session

        # Mock Messages.retrieve_by_chat
        mock_messages = [MagicMock() for _ in range(5)]
        with patch(
            "areyouok_telegram.data.sessions.Messages.retrieve_by_chat",
            return_value=mock_messages,
        ) as mock_retrieve:
            with freeze_time("2025-01-15 11:00:00", tz_offset=0):
                # Get messages
                result = await session.get_messages(mock_async_database_session)

            # Verify the correct time range was used
            mock_retrieve.assert_called_once_with(
                session=mock_async_database_session,
                chat_id="123456",
                from_time=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
                to_time=datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC),  # Current time for active session
            )

            # Verify the result
            assert result == mock_messages

    async def test_get_messages_closed_session(self, mock_async_database_session):
        """Test retrieving messages from a closed session."""
        # Create a closed session instance
        session = Sessions()
        session.chat_id = "123456"
        session.session_start = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.session_end = datetime(2025, 1, 15, 10, 45, 0, tzinfo=UTC)  # Closed session

        # Mock Messages.retrieve_by_chat
        mock_messages = [MagicMock() for _ in range(8)]
        with patch(
            "areyouok_telegram.data.sessions.Messages.retrieve_by_chat",
            return_value=mock_messages,
        ) as mock_retrieve:
            # Get messages
            result = await session.get_messages(mock_async_database_session)

            # Verify the correct time range was used
            mock_retrieve.assert_called_once_with(
                session=mock_async_database_session,
                chat_id="123456",
                from_time=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
                to_time=datetime(2025, 1, 15, 10, 45, 0, tzinfo=UTC),  # Session end time
            )

            # Verify the result
            assert result == mock_messages
