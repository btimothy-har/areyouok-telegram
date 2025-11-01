"""Tests for Context model."""

from datetime import UTC, datetime, timedelta

import pytest

from areyouok_telegram.data.models import Context, ContextType


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_context_encrypt_save_and_get_by_id(mock_db_session, chat_factory, session_factory):
    """Test Context encryption, save, and retrieval by ID."""
    chat, key = chat_factory(id_value=10, telegram_chat_id=1010, with_key_mock=True)
    session = session_factory(chat=chat, id_value=33)

    ctx = Context(chat=chat, type=ContextType.SESSION.value, content={"a": 1}, session_id=session.id)

    class Row:
        id = 9
        chat_id = chat.id
        session_id = session.id
        type = ContextType.SESSION.value
        encrypted_content = "enc"
        created_at = datetime.now(UTC)

    class _ResOne:
        def scalar_one(self):
            return Row()

    mock_db_session.execute.return_value = _ResOne()
    saved = await ctx.save()
    assert saved.id == 9
    assert saved.content == {"a": 1}

    # Now get_by_id should decrypt and return content
    ctx_for_enc = Context(chat=chat, type=ContextType.SESSION.value, content={"a": 1})
    enc_content_str = ctx_for_enc.encrypt_content()

    class Row2:
        id = 9
        chat_id = chat.id
        session_id = session.id
        type = ContextType.SESSION.value
        encrypted_content = enc_content_str
        created_at = datetime.now(UTC)

    class _ScalarsFirst:
        def scalars(self):
            class _S:
                def first(self):
                    return Row2()

            return _S()

    mock_db_session.execute.return_value = _ScalarsFirst()
    fetched = await Context.get_by_id(chat, context_id=9)
    assert fetched and fetched.content == {"a": 1}


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_context_get_by_chat_filters(mock_db_session, chat_factory, session_factory):
    """Test Context.get_by_chat() with multiple filters."""
    chat, key = chat_factory(id_value=12, telegram_chat_id=1212, with_key_mock=True)
    session = session_factory(chat=chat, id_value=34)

    encrypted = Context(chat=chat, type=ContextType.MEMORY.value, content=[1, 2, 3]).encrypt_content()

    class Row:
        id = 1
        chat_id = chat.id
        session_id = session.id
        type = ContextType.MEMORY.value
        encrypted_content = encrypted
        created_at = datetime.now(UTC)

    class _ScalarsAll:
        def scalars(self):
            class _S:
                def all(self):
                    return [Row()]

            return _S()

    mock_db_session.execute.return_value = _ScalarsAll()

    items = await Context.get_by_chat(
        chat,
        session=session,
        ctype=ContextType.MEMORY.value,
        from_timestamp=datetime.now(UTC) - timedelta(days=1),
        to_timestamp=datetime.now(UTC),
    )
    assert len(items) == 1 and items[0].content == [1, 2, 3]


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_context_same_content_different_times(mock_db_session, chat_factory):
    """Test that identical content can be saved at different times."""
    chat, key = chat_factory(id_value=15, telegram_chat_id=1515, with_key_mock=True)

    # Create two contexts with identical content but different timestamps
    content = {"action": "same_action", "value": 42}
    time1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    time2 = datetime(2024, 1, 1, 12, 0, 1, tzinfo=UTC)  # 1 second later

    ctx1 = Context(chat=chat, type=ContextType.ACTION.value, content=content, created_at=time1)
    ctx2 = Context(chat=chat, type=ContextType.ACTION.value, content=content, created_at=time2)

    # Verify they have different object keys due to different timestamps
    assert ctx1.object_key != ctx2.object_key

    # Mock save for ctx1
    class Row1:
        id = 10
        chat_id = chat.id
        session_id = None
        type = ContextType.ACTION.value
        encrypted_content = "enc1"
        created_at = time1

    class _ResOne1:
        def scalar_one(self):
            return Row1()

    mock_db_session.execute.return_value = _ResOne1()
    saved1 = await ctx1.save()
    assert saved1.id == 10

    # Mock save for ctx2
    class Row2:
        id = 11
        chat_id = chat.id
        session_id = None
        type = ContextType.ACTION.value
        encrypted_content = "enc2"
        created_at = time2

    class _ResOne2:
        def scalar_one(self):
            return Row2()

    mock_db_session.execute.return_value = _ResOne2()
    saved2 = await ctx2.save()
    assert saved2.id == 11

    # Both saves should succeed with different IDs
    assert saved1.id != saved2.id
