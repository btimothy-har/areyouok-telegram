"""Tests for Session model."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from areyouok_telegram.data.models import Chat, Session


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_session_new_message_and_activity(chat_factory, session_factory):
    """Test Session.new_message() updates timestamps and message count."""
    chat = chat_factory(id_value=20)
    session = session_factory(chat=chat, id_value=77)

    # Create the expected updated session
    updated_session = Session(
        id=77,
        chat=chat,
        session_start=session.session_start,
        last_user_message=datetime.now(UTC),
        last_user_activity=datetime.now(UTC),
        message_count=1,
    )

    # Patch save to return the updated session
    with patch.object(Session, "save", new=AsyncMock(return_value=updated_session)):
        result = await session.new_message(timestamp=updated_session.last_user_message, is_user=True)

    assert result.message_count == 1
    assert result.last_user_message == updated_session.last_user_message


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_session_get_sessions_filters(mock_db_session):
    """Test Session.get_sessions() with active filter."""
    chat = Chat(telegram_chat_id=321, type="private", id=33, encrypted_key="enc")

    class Row:
        id = 1
        chat_id = chat.id
        session_start = datetime.now(UTC) - timedelta(hours=2)
        session_end = None
        last_user_message = None
        last_user_activity = None
        last_bot_message = None
        last_bot_activity = None
        message_count = 0

    class _ScalarsAll:
        def scalars(self):
            class _S:
                def all(self):
                    return [Row()]

            return _S()

    mock_db_session.execute.return_value = _ScalarsAll()

    items = await Session.get_sessions(chat=chat, active=True)
    assert len(items) == 1 and items[0].chat.id == chat.id
