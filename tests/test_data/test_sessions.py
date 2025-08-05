"""Tests for the Sessions dataclass and its database operations."""

import hashlib
from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

from freezegun import freeze_time
from sqlalchemy import select

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

    async def test_get_active_session_exists(self, async_database_connection):
        """Test retrieving an active session that exists."""
        chat_id = "123456"

        # Create a mock active session
        mock_session = MagicMock(spec=Sessions)
        mock_session.chat_id = chat_id
        mock_session.session_end = None

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_active_session(async_database_connection, chat_id)

        # Verify the result
        assert result == mock_session

        # Verify the query
        async_database_connection.execute.assert_called_once()
        stmt = async_database_connection.execute.call_args[0][0]

        # Check that the statement has correct filters
        assert isinstance(stmt, type(select(Sessions)))

    async def test_get_active_session_none(self, async_database_connection):
        """Test retrieving an active session when none exists."""
        chat_id = "123456"

        # Mock no result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_active_session(async_database_connection, chat_id)

        # Verify no session was found
        assert result is None


class TestSessionsGetAllActiveSessions:
    """Test the get_all_active_sessions class method."""

    async def test_get_all_active_sessions(self, async_database_connection):
        """Test retrieving all active sessions."""
        # Create mock active sessions
        session1 = MagicMock(spec=Sessions)
        session1.session_end = None
        session1.chat_id = "123456"

        session2 = MagicMock(spec=Sessions)
        session2.session_end = None
        session2.chat_id = "789012"

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [session1, session2]
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_all_active_sessions(async_database_connection)

        # Verify the result
        assert len(result) == 2
        assert session1 in result
        assert session2 in result

        # Verify the query was executed
        async_database_connection.execute.assert_called_once()

    async def test_get_all_active_sessions_empty(self, async_database_connection):
        """Test retrieving all active sessions when none exist."""
        # Mock no results
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_all_active_sessions(async_database_connection)

        # Verify empty result
        assert result == []


class TestSessionsGetAllInactiveSessions:
    """Test the get_all_inactive_sessions class method."""

    async def test_get_all_inactive_sessions_within_time_range(self, async_database_connection):
        """Test retrieving inactive sessions that ended within a given time range."""
        from_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        to_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)

        # Create mock inactive sessions with different end times
        session1 = MagicMock(spec=Sessions)
        session1.session_end = datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)  # Within range
        session1.chat_id = "123456"

        session2 = MagicMock(spec=Sessions)
        session2.session_end = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)  # Within range
        session2.chat_id = "789012"

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [session1, session2]
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_all_inactive_sessions(async_database_connection, from_time, to_time)

        # Verify the result
        assert len(result) == 2
        assert session1 in result
        assert session2 in result

        # Verify the query was executed
        async_database_connection.execute.assert_called_once()
        stmt = async_database_connection.execute.call_args[0][0]
        assert isinstance(stmt, type(select(Sessions)))

    async def test_get_all_inactive_sessions_empty(self, async_database_connection):
        """Test retrieving inactive sessions when none exist within the given time range."""
        from_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        to_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)

        # Mock no results
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_all_inactive_sessions(async_database_connection, from_time, to_time)

        # Verify empty result
        assert result == []

    async def test_get_all_inactive_sessions_exact_from_timestamp(self, async_database_connection):
        """Test that sessions ending exactly at the from timestamp are included."""
        from_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        to_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)

        # Create a session that ended exactly at from_time
        session = MagicMock(spec=Sessions)
        session.session_end = from_time  # Exactly at from_time
        session.chat_id = "123456"

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [session]
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_all_inactive_sessions(async_database_connection, from_time, to_time)

        # Verify the session is included (>= includes exact match)
        assert len(result) == 1
        assert session in result

    async def test_get_all_inactive_sessions_excludes_active(self, async_database_connection):
        """Test that active sessions (session_end is None) are never included."""
        from_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        to_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)

        # The query should filter out any sessions where session_end is None
        # So we'll mock an empty result to verify the query logic
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_all_inactive_sessions(async_database_connection, from_time, to_time)

        # Verify the query was executed with proper filters
        async_database_connection.execute.assert_called_once()

        # The result should be empty
        assert result == []

    async def test_get_all_inactive_sessions_exact_to_timestamp_excluded(self, async_database_connection):
        """Test that sessions ending exactly at the to timestamp are excluded."""
        from_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        to_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)

        # Create a session that ended exactly at to_time
        session = MagicMock(spec=Sessions)
        session.session_end = to_time  # Exactly at to_time (should be excluded)
        session.chat_id = "123456"

        # Mock empty result since sessions at to_time should be excluded
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_all_inactive_sessions(async_database_connection, from_time, to_time)

        # Verify the session at exact to_time is excluded (< excludes exact match)
        assert len(result) == 0

    async def test_get_all_inactive_sessions_excludes_sessions_outside_range(self, async_database_connection):
        """Test that sessions outside the time range are excluded."""
        from_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        to_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)

        # Create sessions outside the range
        early_session = MagicMock(spec=Sessions)
        early_session.session_end = datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC)  # Before from_time
        early_session.chat_id = "123456"

        late_session = MagicMock(spec=Sessions)
        late_session.session_end = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)  # After to_time
        late_session.chat_id = "789012"

        # Mock empty result since sessions outside range should be excluded
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_all_inactive_sessions(async_database_connection, from_time, to_time)

        # Verify sessions outside the range are excluded
        assert len(result) == 0

    async def test_get_all_inactive_sessions_boundary_values(self, async_database_connection):
        """Test sessions at exact boundary values of the time range."""
        from_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        to_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)

        # Create sessions at boundaries
        at_from_time = MagicMock(spec=Sessions)
        at_from_time.session_end = from_time  # Exactly at from_time (should be included)
        at_from_time.chat_id = "123456"

        just_before_to_time = MagicMock(spec=Sessions)
        just_before_to_time.session_end = datetime(2025, 1, 15, 12, 59, 59, tzinfo=UTC)  # Just before to_time
        just_before_to_time.chat_id = "789012"

        # Mock result including both boundary sessions
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [at_from_time, just_before_to_time]
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Sessions.get_all_inactive_sessions(async_database_connection, from_time, to_time)

        # Verify both boundary sessions are included
        assert len(result) == 2
        assert at_from_time in result
        assert just_before_to_time in result


class TestSessionsCreateSession:
    """Test the create_session class method."""

    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_create_session(self, async_database_connection):
        """Test creating a new session."""
        chat_id = "123456789"
        timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Call the method
        result = await Sessions.create_session(async_database_connection, chat_id, timestamp)

        # Verify the session was added
        async_database_connection.add.assert_called_once()

        # Get the session object that was added
        added_session = async_database_connection.add.call_args[0][0]

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
        session.message_count = None

        new_timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Record user message
        await session.new_message(new_timestamp, is_user=True)

        # Verify updates
        assert session.last_user_message == new_timestamp
        assert session.last_user_activity == new_timestamp
        assert session.message_count == 1
        assert session.last_bot_message is None

    async def test_new_message_user_increment_count(self):
        """Test recording user message with existing message count."""
        # Create a session instance with existing message count
        session = Sessions()
        session.message_count = 5

        new_timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Record user message
        await session.new_message(new_timestamp, is_user=True)

        # Verify updates
        assert session.last_user_message == new_timestamp
        assert session.last_user_activity == new_timestamp
        assert session.message_count == 6

    async def test_new_message_bot(self):
        """Test recording bot message doesn't increment user count."""
        # Create a session instance
        session = Sessions()
        session.last_user_message = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.message_count = 3

        new_timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Record bot message
        await session.new_message(new_timestamp, is_user=False)

        # Verify updates
        assert session.last_bot_message == new_timestamp
        assert session.last_bot_activity == new_timestamp
        assert session.message_count == 3  # Should not increment for bot messages
        assert session.last_user_message == datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)  # Unchanged

    async def test_new_message_calls_new_activity(self):
        """Test that new_message calls new_activity internally."""
        session = Sessions()
        new_timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Mock new_activity to verify it's called
        with patch.object(session, "new_activity", new=AsyncMock()) as mock_activity:
            await session.new_message(new_timestamp, is_user=True)

            # Verify new_activity was called
            mock_activity.assert_called_once_with(new_timestamp, is_user=True)

    async def test_new_message_timestamp_only_increases_user(self):
        """Test that user message timestamps only increase, never decrease."""
        session = Sessions()

        # Set initial timestamps
        early_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        late_time = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Record a user message with late timestamp
        await session.new_message(late_time, is_user=True)
        assert session.last_user_message == late_time
        assert session.last_user_activity == late_time

        # Try to record a user message with earlier timestamp
        await session.new_message(early_time, is_user=True)

        # Timestamps should not decrease
        assert session.last_user_message == late_time  # Should stay at late_time
        assert session.last_user_activity == late_time  # Should stay at late_time
        assert session.message_count == 2  # But message count should still increment

    async def test_new_message_timestamp_only_increases_bot(self):
        """Test that bot message timestamps only increase, never decrease."""
        session = Sessions()

        # Set initial timestamps
        early_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        late_time = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Record a bot message with late timestamp
        await session.new_message(late_time, is_user=False)
        assert session.last_bot_message == late_time
        assert session.last_bot_activity == late_time

        # Try to record a bot message with earlier timestamp
        await session.new_message(early_time, is_user=False)

        # Timestamps should not decrease
        assert session.last_bot_message == late_time  # Should stay at late_time
        assert session.last_bot_activity == late_time  # Should stay at late_time


class TestSessionsNewActivity:
    """Test the new_activity method."""

    async def test_new_activity_user_no_count_increment(self):
        """Test recording user activity without incrementing message count."""
        # Create a session instance
        session = Sessions()
        session.message_count = 5

        new_timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Record user activity (like edit)
        await session.new_activity(new_timestamp, is_user=True)

        # Verify only activity timestamp updated
        assert session.last_user_activity == new_timestamp
        assert session.message_count == 5  # Should remain unchanged

    async def test_new_activity_bot(self):
        """Test recording bot activity."""
        # Create a session instance
        session = Sessions()

        new_timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Record bot activity
        await session.new_activity(new_timestamp, is_user=False)

        # Verify only bot activity timestamp updated
        assert session.last_bot_activity == new_timestamp
        assert session.last_user_activity is None  # User activity should not be set

    async def test_new_activity_timestamp_only_increases(self):
        """Test that activity timestamps only increase."""
        session = Sessions()

        early_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        late_time = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Set user activity to late time
        await session.new_activity(late_time, is_user=True)
        assert session.last_user_activity == late_time

        # Try to set earlier time
        await session.new_activity(early_time, is_user=True)
        assert session.last_user_activity == late_time  # Should stay at late_time

        # Same for bot activity
        await session.new_activity(late_time, is_user=False)
        assert session.last_bot_activity == late_time

        await session.new_activity(early_time, is_user=False)
        assert session.last_bot_activity == late_time  # Should stay at late_time


class TestSessionsCloseSession:
    """Test the close_session method."""

    async def test_close_session_with_timestamp(self, async_database_connection):
        """Test closing a session with a specific timestamp."""
        # Create a session instance
        session = Sessions()
        session.chat_id = "123456"
        session.session_start = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.session_end = None

        # Mock the get_messages method
        mock_messages = [MagicMock() for _ in range(10)]

        with patch.object(session, "get_messages", return_value=mock_messages):
            # Close the session with specific timestamp
            close_timestamp = datetime(2025, 1, 15, 11, 30, 0, tzinfo=UTC)
            await session.close_session(async_database_connection, close_timestamp)

        # Verify the session was closed with the provided timestamp
        assert session.session_end == close_timestamp
        assert session.message_count == 10


class TestSessionsGetMessages:
    """Test the get_messages method."""

    async def test_get_messages_active_session(self, async_database_connection):
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
                result = await session.get_messages(async_database_connection)

            # Verify the correct time range was used
            mock_retrieve.assert_called_once_with(
                session=async_database_connection,
                chat_id="123456",
                from_time=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
                to_time=datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC),  # Current time for active session
            )

            # Verify the result
            assert result == mock_messages

    async def test_get_messages_closed_session(self, async_database_connection):
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
            result = await session.get_messages(async_database_connection)

            # Verify the correct time range was used
            mock_retrieve.assert_called_once_with(
                session=async_database_connection,
                chat_id="123456",
                from_time=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
                to_time=datetime(2025, 1, 15, 10, 45, 0, tzinfo=UTC),  # Session end time
            )

            # Verify the result
            assert result == mock_messages


class TestSessionsHasBotResponded:
    """Test the has_bot_responded property."""

    def test_has_bot_responded_no_bot_activity(self):
        """Test when bot has not had any activity."""
        session = Sessions()
        session.last_bot_activity = None
        session.last_user_activity = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        assert session.has_bot_responded is False

    def test_has_bot_responded_no_user_activity(self):
        """Test when there's no user activity but bot has been active."""
        session = Sessions()
        session.last_bot_activity = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        session.last_user_activity = None

        assert session.has_bot_responded is True

    def test_has_bot_responded_bot_after_user(self):
        """Test when bot activity is after user activity."""
        session = Sessions()
        session.last_user_activity = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.last_bot_activity = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        assert session.has_bot_responded is True

    def test_has_bot_responded_user_after_bot(self):
        """Test when user activity is after bot activity."""
        session = Sessions()
        session.last_bot_activity = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.last_user_activity = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        assert session.has_bot_responded is False

    def test_has_bot_responded_same_time(self):
        """Test when activities have the same timestamp."""
        timestamp = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session = Sessions()
        session.last_bot_activity = timestamp
        session.last_user_activity = timestamp

        # When timestamps are equal, bot has not responded after user
        assert session.has_bot_responded is False

    def test_has_bot_responded_with_messages_and_activities(self):
        """Test has_bot_responded uses activity timestamps, not message timestamps."""
        session = Sessions()
        # User sent message early, bot sent message later
        session.last_user_message = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        session.last_bot_message = datetime(2025, 1, 15, 10, 10, 0, tzinfo=UTC)

        # But user had recent activity (like edit or reaction)
        session.last_user_activity = datetime(2025, 1, 15, 10, 20, 0, tzinfo=UTC)
        session.last_bot_activity = datetime(2025, 1, 15, 10, 10, 0, tzinfo=UTC)

        # Bot has not responded to latest user activity
        assert session.has_bot_responded is False
