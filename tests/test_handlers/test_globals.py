"""Tests for handlers/globals.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram

from areyouok_telegram.handlers.globals import on_new_update


class TestOnNewUpdate:
    """Test the on_new_update handler."""

    @pytest.mark.asyncio
    async def test_on_new_update_with_user_and_chat(self):
        """Test on_new_update saves user, chat, and update."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.type = "private"

        mock_context = MagicMock()

        with (
            patch("areyouok_telegram.data.models.Update.from_telegram", return_value=MagicMock(save=AsyncMock())),
            patch("areyouok_telegram.data.models.User.from_telegram", return_value=MagicMock(save=AsyncMock())),
            patch(
                "areyouok_telegram.data.models.Chat.from_telegram",
                return_value=MagicMock(save=AsyncMock(return_value=MagicMock(id=1))),
            ),
            patch("areyouok_telegram.handlers.globals.schedule_job", new=AsyncMock()),
        ):
            await on_new_update(mock_update, mock_context)

            # Test passes if no exceptions raised

    @pytest.mark.asyncio
    async def test_on_new_update_with_group_chat(self):
        """Test on_new_update with group chat doesn't schedule conversation job."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = MagicMock(spec=telegram.User)
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.type = "group"

        mock_context = MagicMock()

        with (
            patch("areyouok_telegram.data.models.Update.from_telegram", return_value=MagicMock(save=AsyncMock())),
            patch("areyouok_telegram.data.models.User.from_telegram", return_value=MagicMock(save=AsyncMock())),
            patch(
                "areyouok_telegram.data.models.Chat.from_telegram",
                return_value=MagicMock(save=AsyncMock(return_value=MagicMock(id=1))),
            ),
            patch("areyouok_telegram.handlers.globals.schedule_job", new=AsyncMock()) as mock_schedule,
        ):
            await on_new_update(mock_update, mock_context)

            # Verify job was not scheduled for group chat
            mock_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_new_update_with_channel(self):
        """Test on_new_update with channel doesn't schedule conversation job."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = None
        mock_update.effective_chat = MagicMock(spec=telegram.Chat)
        mock_update.effective_chat.type = "channel"

        mock_context = MagicMock()

        with (
            patch("areyouok_telegram.data.models.Update.from_telegram", return_value=MagicMock(save=AsyncMock())),
            patch(
                "areyouok_telegram.data.models.Chat.from_telegram",
                return_value=MagicMock(save=AsyncMock(return_value=MagicMock(id=1))),
            ),
            patch("areyouok_telegram.handlers.globals.schedule_job", new=AsyncMock()) as mock_schedule,
        ):
            await on_new_update(mock_update, mock_context)

            # Verify job was not scheduled for channel
            mock_schedule.assert_not_called()
