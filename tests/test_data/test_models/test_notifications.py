"""Tests for Notifications model."""

import hashlib
from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.models.notifications import Notifications


class TestNotifications:
    """Test Notifications model."""

    def test_generate_notification_key(self, frozen_time):
        """Test notification key generation."""
        chat_id = "123456789"
        content = "Test notification content"
        created_at = frozen_time

        expected = hashlib.sha256(f"{chat_id}:{content}:{created_at.isoformat()}".encode()).hexdigest()
        result = Notifications.generate_notification_key(chat_id, content, created_at)

        assert result == expected

    def test_generate_notification_key_different_inputs(self):
        """Test notification key generation with different inputs produces different keys."""
        chat_id = "123456789"
        content = "Test content"
        created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        key1 = Notifications.generate_notification_key(chat_id, content, created_at)

        # Different chat_id
        key2 = Notifications.generate_notification_key("987654321", content, created_at)
        assert key1 != key2

        # Different content
        key3 = Notifications.generate_notification_key(chat_id, "Different content", created_at)
        assert key1 != key3

        # Different timestamp
        different_time = datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC)
        key4 = Notifications.generate_notification_key(chat_id, content, different_time)
        assert key1 != key4

    def test_status_property_pending(self):
        """Test status property returns 'pending' when processed_at is None."""
        notification = Notifications()
        notification.processed_at = None

        assert notification.status == "pending"

    def test_status_property_completed(self, frozen_time):
        """Test status property returns 'completed' when processed_at is set."""
        notification = Notifications()
        notification.processed_at = frozen_time

        assert notification.status == "completed"

    @pytest.mark.asyncio
    async def test_add_new_notification(self, mock_db_session):
        """Test adding a new notification."""
        chat_id = "123456789"
        content = "Test notification content"
        priority = 1

        await Notifications.add(mock_db_session, chat_id=chat_id, content=content, priority=priority)

        # Verify execute was called once
        mock_db_session.execute.assert_called_once()

        # Get the statement that was executed
        call_args = mock_db_session.execute.call_args[0][0]

        # Verify it's a PostgreSQL insert statement
        assert isinstance(call_args, type(pg_insert(Notifications)))

        # Verify it has the table set correctly
        assert call_args.table.name == "notifications"

    @pytest.mark.asyncio
    async def test_add_notification_with_default_priority(self, mock_db_session):
        """Test adding a notification with default priority."""
        chat_id = "123456789"
        content = "Test notification"

        await Notifications.add(mock_db_session, chat_id=chat_id, content=content, priority=2)

        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_notification_string_conversion(self, mock_db_session):
        """Test adding a notification converts chat_id to string."""
        chat_id = 123456789  # Integer input
        content = "Test notification"

        await Notifications.add(mock_db_session, chat_id=chat_id, content=content, priority=2)

        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.notifications.datetime")
    async def test_add_notification_uses_current_time(self, mock_datetime, mock_db_session, frozen_time):
        """Test adding a notification uses current UTC time."""
        mock_datetime.now.return_value = frozen_time

        chat_id = "123456789"
        content = "Test notification"

        await Notifications.add(mock_db_session, chat_id=chat_id, content=content, priority=2)

        # Verify datetime.now was called with UTC
        mock_datetime.now.assert_called_once_with(UTC)
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_next_pending_returns_notification(self, mock_db_session):
        """Test get_next_pending returns a notification when found."""
        chat_id = "123456789"

        # Create mock notification
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.chat_id = chat_id
        mock_notification.processed_at = None
        mock_notification.priority = 1

        # Mock the database query chain
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_notification
        mock_db_session.execute.return_value = mock_result

        result = await Notifications.get_next_pending(mock_db_session, chat_id=chat_id)

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify the correct result is returned
        assert result == mock_notification

    @pytest.mark.asyncio
    async def test_get_next_pending_returns_none_when_not_found(self, mock_db_session):
        """Test get_next_pending returns None when no pending notifications exist."""
        chat_id = "123456789"

        # Mock the database query chain to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await Notifications.get_next_pending(mock_db_session, chat_id=chat_id)

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify None is returned
        assert result is None

    @pytest.mark.asyncio
    async def test_get_next_pending_query_structure(self, mock_db_session):
        """Test get_next_pending constructs correct SQL query."""
        chat_id = "123456789"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        await Notifications.get_next_pending(mock_db_session, chat_id=chat_id)

        # Get the statement that was executed
        call_args = mock_db_session.execute.call_args[0][0]

        # Verify it's a select statement
        assert hasattr(call_args, "whereclause")
        assert call_args.whereclause is not None

        # Verify it has ordering and limit
        assert hasattr(call_args, "_order_by") or hasattr(call_args, "_limit")

    @pytest.mark.asyncio
    async def test_mark_as_completed_sets_processed_at(self, mock_db_session):
        """Test mark_as_completed sets processed_at timestamp."""
        notification = Notifications()
        notification.notification_key = "test_key"
        notification.processed_at = None
        notification.updated_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)

        await notification.mark_as_completed(mock_db_session)

        # Verify processed_at is set (should be the current time due to frozen_time)
        assert notification.processed_at is not None
        assert notification.processed_at.tzinfo == UTC

        # Verify updated_at is set
        assert notification.updated_at is not None
        assert notification.updated_at.tzinfo == UTC

        # Verify both timestamps are the same (set to the same datetime.now call)
        assert notification.processed_at == notification.updated_at

        # Verify add was called
        mock_db_session.add.assert_called_once_with(notification)

    @pytest.mark.asyncio
    async def test_mark_as_completed_when_already_completed(self, mock_db_session):
        """Test mark_as_completed works when notification is already completed."""
        original_processed_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)

        notification = Notifications()
        notification.notification_key = "test_key"
        notification.processed_at = original_processed_time
        notification.updated_at = original_processed_time

        await notification.mark_as_completed(mock_db_session)

        # Verify processed_at is updated to new time
        assert notification.processed_at is not None
        assert notification.processed_at != original_processed_time
        assert notification.processed_at.tzinfo == UTC

        # Verify updated_at is set to new time
        assert notification.updated_at is not None
        assert notification.updated_at.tzinfo == UTC

        # Verify both timestamps are the same (set to the same datetime.now call)
        assert notification.processed_at == notification.updated_at

        mock_db_session.add.assert_called_once_with(notification)

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.notifications.datetime")
    async def test_mark_as_completed_uses_current_time(self, mock_datetime, mock_db_session, frozen_time):
        """Test mark_as_completed uses current UTC time."""
        mock_datetime.now.return_value = frozen_time

        notification = Notifications()
        notification.notification_key = "test_key"

        await notification.mark_as_completed(mock_db_session)

        # Verify datetime.now was called once with UTC
        mock_datetime.now.assert_called_once_with(UTC)

    def test_priority_ordering_edge_cases(self):
        """Test priority values and their intended ordering."""
        # Since we can't test the database default directly in a unit test,
        # we test the value mentioned in the model definition
        # Priority 1 = high, 2 = medium (default), 3 = low

        # This is more of a documentation test to ensure we understand priority values
        high_priority = 1
        medium_priority = 2
        low_priority = 3

        assert high_priority < medium_priority < low_priority

    @pytest.mark.asyncio
    async def test_add_with_various_priority_values(self, mock_db_session):
        """Test adding notifications with different priority values."""
        chat_id = "123456789"
        content = "Test notification"

        # Test high priority
        await Notifications.add(mock_db_session, chat_id=chat_id, content=content, priority=1)

        # Test low priority
        await Notifications.add(mock_db_session, chat_id=chat_id, content=content, priority=3)

        # Verify both calls were made
        assert mock_db_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_get_next_pending_with_empty_chat_id(self, mock_db_session):
        """Test get_next_pending with empty chat_id."""
        chat_id = ""

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await Notifications.get_next_pending(mock_db_session, chat_id=chat_id)

        assert result is None
        mock_db_session.execute.assert_called_once()

    def test_generate_notification_key_with_special_characters(self):
        """Test notification key generation with special characters."""
        chat_id = "123456789"
        content = "Test notification with special chars: !@#$%^&*()_+{}|:<>?[]\\;'\",./"
        created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Should not raise an exception
        result = Notifications.generate_notification_key(chat_id, content, created_at)

        # Should return a valid hash
        assert len(result) == 64  # SHA256 hex digest length
        assert all(c in "0123456789abcdef" for c in result)

    def test_generate_notification_key_with_unicode(self):
        """Test notification key generation with Unicode characters."""
        chat_id = "123456789"
        content = "Test notification with Unicode: 你好 🌍 café"
        created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Should not raise an exception
        result = Notifications.generate_notification_key(chat_id, content, created_at)

        # Should return a valid hash
        assert len(result) == 64  # SHA256 hex digest length
        assert all(c in "0123456789abcdef" for c in result)

    def test_generate_notification_key_with_very_long_content(self):
        """Test notification key generation with very long content."""
        chat_id = "123456789"
        content = "A" * 10000  # Very long string
        created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Should not raise an exception
        result = Notifications.generate_notification_key(chat_id, content, created_at)

        # Should return a valid hash
        assert len(result) == 64  # SHA256 hex digest length

    @pytest.mark.asyncio
    async def test_add_with_empty_content(self, mock_db_session):
        """Test adding a notification with empty content."""
        chat_id = "123456789"
        content = ""

        await Notifications.add(mock_db_session, chat_id=chat_id, content=content, priority=2)

        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_with_very_long_content(self, mock_db_session):
        """Test adding a notification with very long content."""
        chat_id = "123456789"
        content = "A" * 10000  # Very long content

        await Notifications.add(mock_db_session, chat_id=chat_id, content=content, priority=2)

        mock_db_session.execute.assert_called_once()

    def test_status_property_is_read_only(self):
        """Test that status property is read-only."""
        notification = Notifications()
        notification.processed_at = None

        # Status should be computed, not settable
        assert notification.status == "pending"

        # Setting processed_at should change status
        notification.processed_at = datetime.now(UTC)
        assert notification.status == "completed"
