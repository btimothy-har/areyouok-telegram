"""Tests for MediaFile model."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from areyouok_telegram.data.models import MediaFile


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_media_file_encrypt_save_and_get_by_message(mock_db_session, chat_factory):
    """Test MediaFile encryption, save, and get_by_message."""
    chat, key = chat_factory(id_value=41, with_key_mock=True)

    mf = MediaFile(
        chat=chat,
        message_id=10,
        file_id="abc",
        file_unique_id="u-1",
        mime_type="image/png",
        bytes_data=b"abc",
    )

    # Mock for save: first execute returns ID
    class MockExecuteResult:
        def scalar_one(self):
            return 3

    mock_db_session.execute.return_value = MockExecuteResult()

    # Create expected saved media file
    saved_mf = MediaFile(
        id=3,
        chat=chat,
        message_id=10,
        file_id="abc",
        file_unique_id="u-1",
        mime_type="image/png",
        bytes_data=b"abc",
        file_size=3,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    # Mock get_by_id to return saved media file
    with patch.object(MediaFile, "get_by_id", new=AsyncMock(return_value=saved_mf)):
        saved = await mf.save()

    assert saved.id == 3
    assert saved.bytes_data == b"abc"

    # Test get_by_message - uses ID-first pattern
    class _ScalarsAll:
        def scalars(self):
            class _S:
                def all(self):
                    return [3]  # Return list of IDs

            return _S()

    mock_db_session.execute.return_value = _ScalarsAll()

    # Mock get_by_id for get_by_message
    with patch.object(MediaFile, "get_by_id", new=AsyncMock(return_value=saved_mf)):
        items = await MediaFile.get_by_message(chat, message_id=10)

    assert len(items) == 1 and items[0].bytes_data == b"abc"


def test_media_file_support_flags(chat_factory):
    """Test MediaFile provider support detection."""
    chat = chat_factory(id_value=42)
    mf = MediaFile(
        chat=chat,
        message_id=1,
        file_id="a",
        file_unique_id="u",
        mime_type="application/pdf",
        bytes_data=b"x",
    )
    assert mf.is_openai_google_supported is True
    assert mf.is_anthropic_supported is True
