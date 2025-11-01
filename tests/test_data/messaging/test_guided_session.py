"""Tests for GuidedSession model."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from areyouok_telegram.data.models import GuidedSession, GuidedSessionState, GuidedSessionType


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_guided_session_save_and_state_flags(chat_factory, session_factory, mock_db_session):
    """Test GuidedSession save and state property flags."""
    chat, key = chat_factory(id_value=30, with_key_mock=True)
    session = session_factory(chat=chat, id_value=88)

    gs = GuidedSession(chat=chat, session=session, session_type=GuidedSessionType.ONBOARDING.value, metadata={"x": 1})

    # Mock for save: first execute returns ID
    class MockExecuteResult:
        def scalar_one(self):
            return 5

    mock_db_session.execute.return_value = MockExecuteResult()

    # Create expected saved guided session
    saved_gs = GuidedSession(
        id=5,
        chat=chat,
        session=session,
        session_type=GuidedSessionType.ONBOARDING.value,
        state=GuidedSessionState.INCOMPLETE.value,
        started_at=gs.started_at,
        completed_at=None,
        metadata={"x": 1},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    # Mock get_by_id to return saved guided session
    with patch.object(GuidedSession, "get_by_id", new=AsyncMock(return_value=saved_gs)):
        result = await gs.save()

    assert result.id == 5
    assert not result.is_completed and not result.is_active and result.is_incomplete


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_guided_session_get_by_chat_decrypts(chat_factory, session_factory, mock_db_session):
    """Test GuidedSession.get_by_chat() decrypts metadata."""
    chat, key = chat_factory(id_value=31, with_key_mock=True)
    session = session_factory(chat=chat, id_value=89)

    # Mock for get_by_chat query (returns IDs)
    class _ScalarsAll:
        def scalars(self):
            class _S:
                def all(self):
                    return [6]  # Return list of IDs

            return _S()

    mock_db_session.execute.return_value = _ScalarsAll()

    # Create expected guided session
    gs = GuidedSession(
        id=6,
        chat=chat,
        session=session,
        session_type=GuidedSessionType.JOURNALING.value,
        state=GuidedSessionState.ACTIVE.value,
        started_at=datetime.now(UTC) - timedelta(minutes=10),
        completed_at=None,
        metadata={"a": 2},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    # Mock GuidedSession.get_by_id to return full guided session
    with patch.object(GuidedSession, "get_by_id", new=AsyncMock(return_value=gs)):
        items = await GuidedSession.get_by_chat(chat, session=session, session_type=GuidedSessionType.JOURNALING.value)

    assert len(items) == 1 and items[0].metadata == {"a": 2}
