"""Tests for CommandUsage model."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from areyouok_telegram.data.models import CommandUsage


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_command_usage_save_success(mock_db_session, chat_factory):
    """Test CommandUsage.save() successful path."""
    chat = chat_factory(id_value=60)
    cu = CommandUsage(chat=chat, command="start", session_id=5)

    # Mock for save: first execute returns ID
    class MockExecuteResult:
        def scalar_one(self):
            return 1

    mock_db_session.execute.return_value = MockExecuteResult()

    # Create expected saved command usage
    saved_cu = CommandUsage(
        id=1,
        chat=chat,
        command="start",
        session_id=5,
        timestamp=datetime.now(UTC),
    )

    # Mock get_by_id to return saved command usage
    with patch.object(CommandUsage, "get_by_id", new=AsyncMock(return_value=saved_cu)):
        result = await cu.save()

    # save() now returns CommandUsage object, not rowcount
    assert isinstance(result, CommandUsage)
    assert result.id == 1
    assert result.command == "start"


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

    # save() returns self on exception
    assert isinstance(result, CommandUsage)
    assert result.command == "test"
    mock_logfire.assert_called_once()
