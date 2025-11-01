"""Tests for Notification model."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from areyouok_telegram.data.models import Notification


def test_notification_status_property():
    """Test Notification.status property based on processed_at."""
    n1 = Notification(chat_id=1, content="msg1")
    assert n1.status == "pending"

    n2 = Notification(chat_id=1, content="msg2", processed_at=datetime.now(UTC))
    assert n2.status == "completed"


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_notification_save_and_get_next_pending(mock_db_session, chat_factory):
    """Test Notification.save() and get_next_pending()."""
    chat = chat_factory(id_value=50)
    notif = Notification(chat_id=chat.id, content="Alert", priority=1)

    # Mock for save: first execute returns ID
    class MockExecuteResult:
        def scalar_one(self):
            return 7

    mock_db_session.execute.return_value = MockExecuteResult()

    # Create expected saved notification
    saved_notification = Notification(
        id=7, chat_id=chat.id, content="Alert", priority=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC)
    )

    # Mock get_by_id to return saved notification
    with patch.object(Notification, "get_by_id", new=AsyncMock(return_value=saved_notification)):
        saved = await notif.save()

    assert saved.id == 7 and saved.status == "pending"

    # Test get_next_pending - uses ID-first pattern
    class _ResOneOrNone:
        def scalar_one_or_none(self):
            return 7  # Return ID only

    mock_db_session.execute.return_value = _ResOneOrNone()

    # Mock get_by_id again for get_next_pending
    with patch.object(Notification, "get_by_id", new=AsyncMock(return_value=saved_notification)):
        next_notif = await Notification.get_next_pending(chat)

    assert next_notif and next_notif.content == "Alert"


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_notification_mark_as_completed(mock_db_session):
    """Test Notification.mark_as_completed() sets processed_at and saves."""
    notif = Notification(chat_id=1, content="Test", id=10)

    # Mock for save: first execute returns ID
    class MockExecuteResult:
        def scalar_one(self):
            return 10

    mock_db_session.execute.return_value = MockExecuteResult()

    # Create expected updated notification
    updated_notification = Notification(
        id=10,
        chat_id=1,
        content="Test",
        priority=2,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        processed_at=datetime.now(UTC),
    )

    # Mock get_by_id to return updated notification
    with patch.object(Notification, "get_by_id", new=AsyncMock(return_value=updated_notification)):
        updated = await notif.mark_as_completed()

    assert updated.processed_at is not None
    assert updated.status == "completed"
