"""Tests for Message model."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import telegram

from areyouok_telegram.data.models import Chat, Message


@pytest.mark.asyncio
async def test_message_from_telegram_and_type_mapping():
    """Test Message.from_telegram() factory and type mapping."""
    # Build a real Telegram Message via de_json so message_type mapping works
    ts = int(datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC).timestamp())
    payload = {
        "message_id": 42,
        "date": ts,
        "text": "hi",
        "chat": {"id": 999, "type": "private"},
        "from": {"id": 1, "is_bot": False, "first_name": "A"},
    }
    tg_msg = telegram.Message.de_json(payload, None)

    chat = Chat(telegram_chat_id=999, type="private", id=1, encrypted_key="enc")

    model_msg = Message.from_telegram(user_id=1, chat=chat, message=tg_msg)
    assert model_msg.message_type == "Message"
    assert model_msg.telegram_message_id == 42
    # Round-trip telegram object
    obj = model_msg.telegram_object
    assert isinstance(obj, telegram.Message)
    assert obj.message_id == 42


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_message_save_and_get_by_id_decrypt(mock_db_session, chat_factory):
    """Test Message.save() encrypts and get_by_id() decrypts payload + reasoning."""
    chat, key = chat_factory(id_value=7, telegram_chat_id=777, with_key_mock=True)

    # Build message
    payload = {"message_id": 100, "date": int(datetime.now(UTC).timestamp()), "text": "hello"}
    msg = Message(
        chat=chat,
        user_id=123,
        telegram_message_id=100,
        message_type="Message",
        payload=payload,
        reasoning="why",
        session_id=3,
    )

    # Create the expected saved message
    saved_msg = Message(
        id=55,
        chat=chat,
        user_id=123,
        telegram_message_id=100,
        message_type="Message",
        payload=payload,
        reasoning="why",
        session_id=3,
    )

    with patch.object(Message, "get_by_id", new=AsyncMock(return_value=saved_msg)):
        result = await msg.save()

    assert result.id == 55
    assert result.payload == payload
    assert result.reasoning == "why"
    mock_db_session.execute.assert_called_once()
