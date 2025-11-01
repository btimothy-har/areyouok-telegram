"""Tests for Update model."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import telegram

from areyouok_telegram.data.models import Update


@pytest.mark.asyncio
async def test_update_from_telegram_and_object_key():
    """Test Update.from_telegram() factory and object_key generation."""
    tg_update = telegram.Update(update_id=123)
    tg_update._id_attrs = (123,)  # Required by telegram.Update

    upd = Update.from_telegram(update=tg_update)
    assert upd.telegram_update_id == 123
    assert upd.object_key
    assert len(upd.object_key) == 64  # SHA-256 hex digest


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_update_save(mock_db_session):
    """Test Update.save() upserts the record."""
    upd = Update(telegram_update_id=456, payload={"update_id": 456})

    # Mock for save: first execute returns ID
    class MockExecuteResult:
        def scalar_one(self):
            return 2

    mock_db_session.execute.return_value = MockExecuteResult()

    # Create expected saved update
    saved_update = Update(
        id=2,
        telegram_update_id=456,
        payload={"update_id": 456},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    # Mock get_by_id to return saved update
    with patch.object(Update, "get_by_id", new=AsyncMock(return_value=saved_update)):
        saved = await upd.save()

    assert saved.id == 2
    assert saved.telegram_update_id == 456
