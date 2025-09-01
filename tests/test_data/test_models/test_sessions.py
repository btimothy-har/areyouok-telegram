"""Tests for Sessions model."""

import hashlib
from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram

from areyouok_telegram.data.models.sessions import Sessions


class TestSessions:
    """Test Sessions model."""

    def test_generate_session_key(self):
        """Test session key generation."""
        chat_id = "123"
        session_start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        timestamp_str = session_start.isoformat()
        expected = hashlib.sha256(f"{chat_id}:{timestamp_str}".encode()).hexdigest()

        assert Sessions.generate_session_key(chat_id, session_start) == expected

    def test_session_id_property(self):
        """Test session_id property returns session_key."""
        session = Sessions()
        session.session_key = "test_key_123"

        assert session.session_id == "test_key_123"

    def test_has_bot_responded_no_bot_activity(self):
        """Test has_bot_responded when bot has never responded."""
        session = Sessions()
        session.last_bot_activity = None
        session.last_user_activity = datetime.now(UTC)

        assert session.has_bot_responded is False

    def test_has_bot_responded_no_user_activity(self):
        """Test has_bot_responded when no user activity."""
        session = Sessions()
        session.last_bot_activity = datetime.now(UTC)
        session.last_user_activity = None

        assert session.has_bot_responded is True

    def test_has_bot_responded_bot_after_user(self):
        """Test has_bot_responded when bot responded after user."""
        session = Sessions()
        session.last_user_activity = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        session.last_bot_activity = datetime(2025, 1, 1, 12, 1, 0, tzinfo=UTC)

        assert session.has_bot_responded is True

    def test_has_bot_responded_user_after_bot(self):
        """Test has_bot_responded when user responded after bot."""
        session = Sessions()
        session.last_user_activity = datetime(2025, 1, 1, 12, 1, 0, tzinfo=UTC)
        session.last_bot_activity = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        assert session.has_bot_responded is False

    @pytest.mark.asyncio
    async def test_new_message_user(self, mock_db_session):
        """Test recording a new user message."""
        session = Sessions()
        session.message_count = 5
        session.last_user_message = None
        session.last_user_activity = None

        timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        await session.new_message(mock_db_session, timestamp=timestamp, is_user=True)

        assert session.last_user_message == timestamp
        assert session.last_user_activity == timestamp
        assert session.message_count == 6
        mock_db_session.add.assert_called_with(session)

    @pytest.mark.asyncio
    async def test_new_message_bot(self, mock_db_session):
        """Test recording a new bot message."""
        session = Sessions()
        session.message_count = 5
        session.last_bot_message = None
        session.last_bot_activity = None

        timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        await session.new_message(mock_db_session, timestamp=timestamp, is_user=False)

        assert session.last_bot_message == timestamp
        assert session.last_bot_activity == timestamp
        assert session.message_count == 5  # Bot messages don't increment count
        mock_db_session.add.assert_called_with(session)

    @pytest.mark.asyncio
    async def test_new_activity_user(self, mock_db_session):
        """Test recording user activity."""
        session = Sessions()
        session.last_user_activity = None

        timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        await session.new_activity(mock_db_session, timestamp=timestamp, is_user=True)

        assert session.last_user_activity == timestamp
        mock_db_session.add.assert_called_once_with(session)

    @pytest.mark.asyncio
    async def test_new_activity_updates_max_timestamp(self, mock_db_session):
        """Test activity timestamp only updates if newer."""
        session = Sessions()
        old_timestamp = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
        new_timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        session.last_user_activity = new_timestamp

        # Try to update with older timestamp
        await session.new_activity(mock_db_session, timestamp=old_timestamp, is_user=True)

        # Should keep the newer timestamp
        assert session.last_user_activity == new_timestamp

    @pytest.mark.asyncio
    async def test_close_session(self, mock_db_session):
        """Test closing a session."""
        session = Sessions()
        session.chat_id = "123"
        session.session_start = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)

        # Mock get_messages to return some messages
        mock_messages = [MagicMock(spec=telegram.Message) for _ in range(3)]
        with patch.object(session, "get_messages", new=AsyncMock(return_value=mock_messages)):
            timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
            await session.close_session(mock_db_session, timestamp=timestamp)

        assert session.session_end == timestamp
        assert session.message_count == 3
        mock_db_session.add.assert_called_once_with(session)

    @pytest.mark.asyncio
    async def test_get_messages(self, mock_db_session):
        """Test retrieving messages for a session."""
        session = Sessions()
        session.chat_id = "123"
        session.session_key = "session_123"  # Use session_key, not session_id
        session.session_start = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
        session.session_end = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_messages = [MagicMock(spec=telegram.Message)]

        with patch("areyouok_telegram.data.models.sessions.Messages") as mock_messages_class:
            # Make retrieve_by_session an async mock
            mock_messages_class.retrieve_by_session = AsyncMock(return_value=mock_messages)

            result = await session.get_messages(mock_db_session)

            assert result == mock_messages
            mock_messages_class.retrieve_by_session.assert_called_once_with(mock_db_session, session_id="session_123")

    @pytest.mark.asyncio
    async def test_create_session(self, mock_db_session):
        """Test creating a new session."""
        chat_id = "123"
        timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Create a mock session that will be returned
        mock_session = MagicMock(spec=Sessions)
        mock_session.chat_id = chat_id
        mock_session.session_start = timestamp
        mock_session.session_key = Sessions.generate_session_key(chat_id, timestamp)

        # Mock the database execute result
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_session
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        session = await Sessions.create_session(mock_db_session, chat_id=chat_id, timestamp=timestamp)

        assert session == mock_session
        assert session.chat_id == chat_id
        assert session.session_start == timestamp
        assert session.session_key == Sessions.generate_session_key(chat_id, timestamp)
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_active_session_found(self, mock_db_session):
        """Test retrieving an active session."""
        mock_session = MagicMock(spec=Sessions)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db_session.execute.return_value = mock_result

        result = await Sessions.get_active_session(mock_db_session, chat_id="123")

        assert result == mock_session
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_active_session_not_found(self, mock_db_session):
        """Test retrieving active session when none exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await Sessions.get_active_session(mock_db_session, chat_id="123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_active_sessions(self, mock_db_session):
        """Test retrieving all active sessions."""
        mock_session1 = MagicMock(spec=Sessions)
        mock_session2 = MagicMock(spec=Sessions)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_session1, mock_session2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Sessions.get_all_active_sessions(mock_db_session)

        assert result == [mock_session1, mock_session2]

    @pytest.mark.asyncio
    async def test_get_all_inactive_sessions(self, mock_db_session):
        """Test retrieving inactive sessions within time range."""
        from_dt = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        to_dt = datetime(2025, 1, 1, 14, 0, 0, tzinfo=UTC)

        mock_session = MagicMock(spec=Sessions)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_session]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Sessions.get_all_inactive_sessions(mock_db_session, from_dt, to_dt)

        assert result == [mock_session]
        mock_db_session.execute.assert_called_once()

    def test_is_onboarding_true(self):
        """Test is_onboarding property returns True when onboarding_key is set."""
        session = Sessions()
        session.onboarding_key = "test_onboarding_key_123"

        assert session.is_onboarding is True

    def test_is_onboarding_false(self):
        """Test is_onboarding property returns False when onboarding_key is None."""
        session = Sessions()
        session.onboarding_key = None

        assert session.is_onboarding is False

    @pytest.mark.asyncio
    async def test_create_session_with_onboarding_key(self, mock_db_session):
        """Test creating a session with onboarding_key parameter."""
        chat_id = "123"
        timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        # Create a mock session that will be returned
        mock_session = MagicMock(spec=Sessions)
        mock_session.chat_id = chat_id
        mock_session.session_start = timestamp
        mock_session.session_key = Sessions.generate_session_key(chat_id, timestamp)

        # Mock the database execute result
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_session
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        session = await Sessions.create_session(mock_db_session, chat_id=chat_id, timestamp=timestamp)

        assert session == mock_session
        assert session.chat_id == chat_id
        assert session.session_start == timestamp
        assert session.session_key == Sessions.generate_session_key(chat_id, timestamp)
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_onboarding_key_found(self, mock_db_session):
        """Test retrieving sessions by onboarding_key when sessions exist."""
        onboarding_key = "test_onboarding_key_789"
        mock_session1 = MagicMock(spec=Sessions)
        mock_session2 = MagicMock(spec=Sessions)
        mock_session1.onboarding_key = onboarding_key
        mock_session2.onboarding_key = onboarding_key

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_session1, mock_session2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Sessions.get_by_onboarding_key(mock_db_session, onboarding_key=onboarding_key)

        assert result == [mock_session1, mock_session2]
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_onboarding_key_not_found(self, mock_db_session):
        """Test retrieving sessions by onboarding_key when no sessions exist."""
        onboarding_key = "nonexistent_onboarding_key"

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Sessions.get_by_onboarding_key(mock_db_session, onboarding_key=onboarding_key)

        assert result == []
        mock_db_session.execute.assert_called_once()
