"""Tests for CommandUsage model."""

from unittest.mock import patch

import pytest

from areyouok_telegram.data.models import CommandUsage


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_command_usage_save_success(mock_db_session, chat_factory):
    """Test CommandUsage.save() successful path."""
    chat = chat_factory(id_value=60)
    cu = CommandUsage(chat=chat, command="start", session_id=5)

    class _ResRowCount:
        rowcount = 1

    mock_db_session.execute.return_value = _ResRowCount()
    result = await cu.save()
    assert result == 1


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_command_usage_save_exception_logged(mock_db_session, chat_factory):
    """Test CommandUsage.save() exception path logs to logfire."""
    chat = chat_factory(id_value=61)
    cu = CommandUsage(chat=chat, command="test")

    # Simulate exception during save
    mock_db_session.execute.side_effect = Exception("DB error")

    with patch("areyouok_telegram.data.models.system.command_usage.logfire.exception") as mock_logfire:
        result = await cu.save()

    assert result == 0
    mock_logfire.assert_called_once()
