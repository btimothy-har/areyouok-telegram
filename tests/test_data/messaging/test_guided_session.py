"""Tests for GuidedSession model."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from areyouok_telegram.data.models import GuidedSession, GuidedSessionState, GuidedSessionType


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_guided_session_save_and_state_flags(chat_factory, session_factory, mock_db_session):
    """Test GuidedSession save and state property flags."""
    chat, key = chat_factory(id_value=30, with_key_mock=True)
    session = session_factory(chat=chat, id_value=88)

    gs = GuidedSession(chat=chat, session=session, session_type=GuidedSessionType.ONBOARDING.value, metadata={"x": 1})

    class Row:
        id = 5
        chat_id = chat.id
        session_id = session.id
        session_type = GuidedSessionType.ONBOARDING.value
        state = GuidedSessionState.INCOMPLETE.value
        started_at = gs.started_at
        completed_at = None
        encrypted_metadata = gs.encrypt_metadata()
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)

    class _ResOne:
        def scalar_one(self):
            return Row()

    mock_db_session.execute.return_value = _ResOne()

    result = await gs.save()
    assert result.id == 5
    assert not result.is_completed and not result.is_active and result.is_incomplete


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_guided_session_get_by_chat_decrypts(chat_factory, session_factory, mock_db_session):
    """Test GuidedSession.get_by_chat() decrypts metadata."""
    chat, key = chat_factory(id_value=31, with_key_mock=True)
    session = session_factory(chat=chat, id_value=89)

    gs_for_encryption = GuidedSession(
        chat=chat, session=session, session_type=GuidedSessionType.JOURNALING.value, metadata={"a": 2}
    )
    encrypted = gs_for_encryption.encrypt_metadata()

    class Row:
        id = 6
        chat_id = chat.id
        session_id = session.id
        session_type = GuidedSessionType.JOURNALING.value
        state = GuidedSessionState.ACTIVE.value
        started_at = datetime.now(UTC) - timedelta(minutes=10)
        completed_at = None
        encrypted_metadata = encrypted
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)

    # get_by_chat will call Session.get_by_id; mock it
    async def _get_by_id_mock(*, session_id: int):
        return session if session_id == session.id else None

    with patch("areyouok_telegram.data.models.messaging.session.Session.get_by_id", _get_by_id_mock):

        class _ScalarsAll:
            def scalars(self):
                class _S:
                    def all(self):
                        return [Row()]

                return _S()

        mock_db_session.execute.return_value = _ScalarsAll()

        items = await GuidedSession.get_by_chat(chat, session=session, session_type=GuidedSessionType.JOURNALING.value)
        assert len(items) == 1 and items[0].metadata == {"a": 2}
