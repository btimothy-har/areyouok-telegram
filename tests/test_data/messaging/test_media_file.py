"""Tests for MediaFile model."""

from datetime import UTC, datetime

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

    class Row:
        id = 3
        chat_id = chat.id
        message_id = 10
        file_id = "abc"
        file_unique_id = "u-1"
        mime_type = "image/png"
        file_size = 3
        encrypted_content_base64 = mf.encrypt_content()
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)

    class _ResOne:
        def scalar_one(self):
            return Row()

    mock_db_session.execute.return_value = _ResOne()
    saved = await mf.save()
    assert saved.id == 3
    assert saved.bytes_data == b"abc"

    # Test get_by_message
    class _ScalarsAll:
        def scalars(self):
            class _S:
                def all(self):
                    return [Row()]

            return _S()

    mock_db_session.execute.return_value = _ScalarsAll()
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
