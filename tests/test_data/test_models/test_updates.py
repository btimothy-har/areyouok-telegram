"""Tests for Updates model."""

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest
import telegram

from areyouok_telegram.data.models.updates import Updates


@pytest.fixture
def mock_telegram_update():
    """Create a mock Telegram update."""
    update = MagicMock(spec=telegram.Update)
    update.update_id = 12345
    update.to_json.return_value = '{"update_id": 12345}'
    update.to_dict.return_value = {"update_id": 12345}
    return update


class TestUpdates:
    """Test Updates model."""

    def test_generate_update_key(self):
        """Test update key generation."""
        payload = '{"update_id": 12345}'
        expected = hashlib.sha256(payload.encode()).hexdigest()
        assert Updates.generate_update_key(payload) == expected

    @pytest.mark.asyncio
    async def test_new_or_upsert_new_update(self, mock_db_session, mock_telegram_update):
        """Test inserting a new update."""
        mock_result = AsyncMock()
        mock_db_session.execute.return_value = mock_result

        await Updates.new_or_upsert(mock_db_session, update=mock_telegram_update)

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify the statement is for updates table
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "table")
        assert call_args.table.name == "updates"

    @pytest.mark.asyncio
    async def test_new_or_upsert_existing_update(self, mock_db_session, mock_telegram_update):
        """Test upserting an existing update."""
        # Change the payload slightly to simulate an update
        mock_telegram_update.to_dict.return_value = {"update_id": 12345, "edited": True}

        await Updates.new_or_upsert(mock_db_session, update=mock_telegram_update)

        # Verify execute was called with upsert
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_new_or_upsert_calls_to_json_and_to_dict(self, mock_db_session, mock_telegram_update):
        """Test that new_or_upsert calls both to_json and to_dict on the update."""
        await Updates.new_or_upsert(mock_db_session, update=mock_telegram_update)

        # Verify both methods were called
        mock_telegram_update.to_json.assert_called_once()
        mock_telegram_update.to_dict.assert_called_once()
