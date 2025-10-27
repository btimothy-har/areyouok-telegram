"""Tests for Notification model."""

from datetime import UTC, datetime

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

    class Row:
        id = 7
        chat_id = chat.id
        content = "Alert"
        priority = 1
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)
        processed_at = None

    class _ResOne:
        def scalar_one(self):
            return Row()

    mock_db_session.execute.return_value = _ResOne()
    saved = await notif.save()
    assert saved.id == 7 and saved.status == "pending"

    # get_next_pending
    class _ResOneOrNone:
        def scalar_one_or_none(self):
            return Row()

    mock_db_session.execute.return_value = _ResOneOrNone()
    next_notif = await Notification.get_next_pending(chat)
    assert next_notif and next_notif.content == "Alert"


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_notification_mark_as_completed(mock_db_session):
    """Test Notification.mark_as_completed() sets processed_at and saves."""
    notif = Notification(chat_id=1, content="Test", id=10)

    class Row:
        id = 10
        chat_id = 1
        content = "Test"
        priority = 2
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)
        processed_at = datetime.now(UTC)

    class _ResOne:
        def scalar_one(self):
            return Row()

    mock_db_session.execute.return_value = _ResOne()
    updated = await notif.mark_as_completed()
    assert updated.processed_at is not None
    assert updated.status == "completed"
