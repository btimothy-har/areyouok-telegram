"""Tests for handlers/errors.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram

from areyouok_telegram.handlers.errors import on_error_event


class TestOnErrorEvent:
    """Test the on_error_event handler."""

    @pytest.mark.asyncio
    async def test_on_error_event_with_update_and_developer_chat(self):
        """Test error handler sends notification to developer chat."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_context = MagicMock()
        mock_context.error = Exception("Test error")
        mock_context.bot = AsyncMock()

        with (
            patch("areyouok_telegram.handlers.errors.DEVELOPER_CHAT_ID", 12345),
            patch("areyouok_telegram.handlers.errors.telegram_call", new=AsyncMock()),
            patch("areyouok_telegram.handlers.errors.logfire.exception") as mock_log,
        ):
            await on_error_event(mock_update, mock_context)

            # Verify error was logged
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_error_event_without_developer_chat(self):
        """Test error handler without developer chat ID configured."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_context = MagicMock()
        mock_context.error = Exception("Test error")

        with (
            patch("areyouok_telegram.handlers.errors.DEVELOPER_CHAT_ID", None),
            patch("areyouok_telegram.handlers.errors.logfire.exception") as mock_log,
        ):
            await on_error_event(mock_update, mock_context)

            # Verify error was logged
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_error_event_network_error_early_return(self):
        """Test that network errors return early without notification."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_context = MagicMock()
        mock_context.error = telegram.error.NetworkError("Network error")
        mock_context.bot = AsyncMock()

        with (
            patch("areyouok_telegram.handlers.errors.DEVELOPER_CHAT_ID", 12345),
            patch("areyouok_telegram.handlers.errors.telegram_call", new=AsyncMock()) as mock_call,
            patch("areyouok_telegram.handlers.errors.logfire.exception"),
        ):
            await on_error_event(mock_update, mock_context)

            # Verify no telegram message sent for network error
            mock_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_error_event_timeout_error_early_return(self):
        """Test that timeout errors return early without notification."""
        mock_update = MagicMock(spec=telegram.Update)
        mock_context = MagicMock()
        mock_context.error = telegram.error.TimedOut("Timeout")
        mock_context.bot = AsyncMock()

        with (
            patch("areyouok_telegram.handlers.errors.DEVELOPER_CHAT_ID", 12345),
            patch("areyouok_telegram.handlers.errors.telegram_call", new=AsyncMock()) as mock_call,
            patch("areyouok_telegram.handlers.errors.logfire.exception"),
        ):
            await on_error_event(mock_update, mock_context)

            # Verify no telegram message sent for timeout error
            mock_call.assert_not_called()
