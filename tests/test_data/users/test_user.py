"""Tests for User model."""

from datetime import UTC, datetime

import pytest

from areyouok_telegram.data.models import User


@pytest.mark.asyncio
async def test_user_from_telegram_and_object_key(mock_telegram_user):
    """Test User.from_telegram() factory and object_key generation."""
    user = User.from_telegram(mock_telegram_user)
    assert user.telegram_user_id == mock_telegram_user.id
    assert user.is_bot == mock_telegram_user.is_bot
    assert user.object_key
    assert len(user.object_key) == 64  # SHA-256 hex digest


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_user_save_and_get_by_id(mock_db_session):
    """Test User.save() and get_by_id() round-trip."""
    user = User(telegram_user_id=12345, is_bot=False, language_code="en")

    class Row:
        id = 9
        telegram_user_id = 12345
        is_bot = False
        language_code = "en"
        is_premium = False
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)

    class MockExecuteResult:
        def scalar_one(self):
            return 9

    class _ScalarsFirst:
        def scalars(self):
            class _S:
                def first(self):
                    return Row()

            return _S()

    # First execute: insert returning ID; second: select in get_by_id
    mock_db_session.execute.side_effect = [MockExecuteResult(), _ScalarsFirst()]

    saved = await user.save()
    assert saved.id == 9
    assert saved.telegram_user_id == 12345
    assert mock_db_session.execute.call_count == 2
