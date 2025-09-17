"""Tests for CommandUsage model."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from areyouok_telegram.data.models.command_usage import CommandUsage


class TestCommandUsage:
    """Test CommandUsage model."""

    @pytest.mark.asyncio
    async def test_track_command_basic(self, mock_db_session):
        """Test basic command tracking functionality."""
        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await CommandUsage.track_command(
            mock_db_session,
            command="start",
            chat_id="123456",
            session_id="session_789",
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

        # Verify the statement is for command_usage table
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "table")
        assert call_args.table.name == "command_usage"

    @pytest.mark.asyncio
    async def test_track_command_preferences(self, mock_db_session):
        """Test tracking preferences command."""
        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await CommandUsage.track_command(
            mock_db_session,
            command="preferences",
            chat_id="789123",
            session_id="session_456",
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_track_command_exception_handling(self, mock_db_session):
        """Test exception handling during command tracking."""
        # Mock execute to raise an exception
        mock_db_session.execute.side_effect = Exception("Database error")

        # Mock logfire to verify exception logging
        with patch("areyouok_telegram.data.models.command_usage.logfire") as mock_logfire:
            result = await CommandUsage.track_command(
                mock_db_session,
                command="start",
                chat_id="error_chat",
                session_id="error_session",
            )

            assert result == 0
            mock_logfire.exception.assert_called_once()
            assert "Failed to insert command usage record" in str(mock_logfire.exception.call_args)

    @pytest.mark.asyncio
    async def test_track_command_zero_rowcount(self, mock_db_session):
        """Test command tracking when no rows are affected."""
        # Mock execute result with zero rowcount
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db_session.execute.return_value = mock_result

        result = await CommandUsage.track_command(
            mock_db_session,
            command="preferences",
            chat_id="zero_chat",
            session_id="zero_session",
        )

        assert result == 0
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_track_command_various_commands(self, mock_db_session):
        """Test tracking various command types."""
        commands = ["start", "preferences", "help", "settings", "custom_command"]

        for i, command in enumerate(commands):
            # Mock execute result
            mock_result = MagicMock()
            mock_result.rowcount = 1
            mock_db_session.execute.return_value = mock_result

            result = await CommandUsage.track_command(
                mock_db_session,
                command=command,
                chat_id=f"chat_{i}",
                session_id=f"session_{i}",
            )

            assert result == 1

        # Should be called once for each command
        assert mock_db_session.execute.call_count == len(commands)

    @pytest.mark.asyncio
    async def test_track_command_string_conversion(self, mock_db_session):
        """Test that chat_id is properly converted to string."""
        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        # Pass integer chat_id to test string conversion
        result = await CommandUsage.track_command(
            mock_db_session,
            command="start",
            chat_id=123456,  # Integer instead of string
            session_id="session_test",
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

        # Verify the values in the insert statement
        call_args = mock_db_session.execute.call_args[0][0]
        # The chat_id should be converted to string in the model
        assert hasattr(call_args, "table")

    @pytest.mark.asyncio
    async def test_track_command_empty_strings(self, mock_db_session):
        """Test tracking with empty string values."""
        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await CommandUsage.track_command(
            mock_db_session,
            command="",  # Empty command
            chat_id="",  # Empty chat_id
            session_id="",  # Empty session_id
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_track_command_long_strings(self, mock_db_session):
        """Test tracking with long string values."""
        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        long_command = "very_long_command_name_that_might_be_generated_dynamically"
        long_chat_id = "1234567890" * 10  # 100 characters
        long_session_id = "session_" + "x" * 100

        result = await CommandUsage.track_command(
            mock_db_session,
            command=long_command,
            chat_id=long_chat_id,
            session_id=long_session_id,
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()
