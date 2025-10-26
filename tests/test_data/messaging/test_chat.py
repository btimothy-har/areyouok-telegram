"""Tests for Chat model."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from areyouok_telegram.data.models import Chat


@pytest.mark.asyncio
async def test_chat_object_key_and_from_telegram(mock_telegram_chat):
    """Test Chat object_key generation and from_telegram factory."""
    chat = Chat.from_telegram(mock_telegram_chat)
    assert chat.object_key
    assert chat.telegram_chat_id == mock_telegram_chat.id
    assert chat.type == mock_telegram_chat.type


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_chat_save_generates_key_and_upserts(mock_db_session):
    """Test Chat.save() generates encryption key and performs upsert."""
    chat = Chat(telegram_chat_id=999, type="private")

    # Mock get_by_id to return saved chat
    saved_chat = Chat(telegram_chat_id=999, type="private", id=1, encrypted_key="enc_key")

    with patch.object(Chat, "get_by_id", new=AsyncMock(return_value=saved_chat)):
        result = await chat.save()

    assert result.id == 1
    assert result.telegram_chat_id == 999
    assert result.encrypted_key
    mock_db_session.execute.assert_called_once()


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_chat_get_by_id_found(mock_db_session):
    """Test Chat.get_by_id() retrieves a chat by internal ID."""

    class Row:
        id = 7
        telegram_chat_id = 123
        type = "group"
        title = "grp"
        is_forum = False
        encrypted_key = "enc"
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)

    class _ScalarsFirst:
        def scalars(self):
            class _S:
                def first(self):
                    return Row()

            return _S()

    mock_db_session.execute.return_value = _ScalarsFirst()

    found = await Chat.get_by_id(chat_id=7)
    assert found and found.id == 7 and found.telegram_chat_id == 123


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_chat_get_filters(mock_db_session):
    """Test Chat.get() with various filters."""

    class Row:
        id = 2
        telegram_chat_id = 456
        type = "private"
        title = None
        is_forum = False
        encrypted_key = "enc"
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)

    class _ScalarsAll:
        def scalars(self):
            class _S:
                def all(self):
                    return [Row()]

            return _S()

    mock_db_session.execute.return_value = _ScalarsAll()

    items = await Chat.get(
        chat_type="private",
        from_timestamp=datetime.now(UTC) - timedelta(days=7),
        to_timestamp=datetime.now(UTC),
        limit=10,
    )
    assert len(items) == 1 and items[0].telegram_chat_id == 456
