"""Tests for ChatEvent helper model."""

from datetime import UTC, datetime

import pytest
import telegram

from areyouok_telegram.data.models import ChatEvent, Context, ContextType, Message


def _tg_message_payload(text="hi", message_id=1):
    """Helper to create a Telegram message payload dict."""
    ts = int(datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC).timestamp())
    return {
        "message_id": message_id,
        "date": ts,
        "text": text,
        "chat": {"id": 999, "type": "private"},
        "from": {"id": 1, "is_bot": False, "first_name": "A"},
    }


@pytest.mark.asyncio
async def test_from_message_and_to_model_message_user(chat_factory):
    """Test ChatEvent.from_message() and to_model_message() for user messages."""
    chat = chat_factory(id_value=1)
    msg = Message.from_telegram(
        user_id=1,
        chat=chat,
        message=telegram.Message.de_json(_tg_message_payload("hello", 10), None),
    )

    ev = ChatEvent.from_message(msg, attachments=[])
    mm = ev.to_model_message(bot_id=999999, ts_reference=datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC))
    assert mm.kind == "request"


@pytest.mark.asyncio
async def test_from_context_action_sets_user(chat_factory):
    """Test ChatEvent.from_context() sets user_id for ACTION type."""
    chat = chat_factory(id_value=2)
    ctx = Context(chat=chat, type=ContextType.ACTION.value, content={"x": 1})
    ev = ChatEvent.from_context(ctx)
    assert ev.user_id == chat.telegram_chat_id
