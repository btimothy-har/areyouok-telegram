"""Test module for LLM utilities."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import logfire
import pydantic_ai
import pytest

from areyouok_telegram.llms.utils import run_agent_with_tracking


class TestRunAgentWithTracking:
    """Test the run_agent_with_tracking function."""

    @pytest.mark.asyncio
    async def test_run_agent_with_tracking_success(self):
        """Test successful agent run with tracking."""
        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_agent.run = AsyncMock()

        # Mock result
        mock_result = MagicMock()
        mock_result.usage.return_value = {"tokens": 100}
        mock_agent.run.return_value = mock_result

        # Mock database and tracking
        with (
            patch("areyouok_telegram.llms.utils.async_database") as mock_db,
            patch("areyouok_telegram.llms.utils.LLMUsage.track_pydantic_usage") as mock_track,
        ):
            mock_db_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_db_conn

            result = await run_agent_with_tracking(
                agent=mock_agent, chat_id="123", session_id="session123", run_kwargs={"message_history": []}
            )

            # Verify agent was called
            mock_agent.run.assert_called_once_with(message_history=[])

            # Verify tracking was called
            mock_track.assert_called_once_with(
                db_conn=mock_db_conn,
                chat_id="123",
                session_id="session123",
                agent=mock_agent,
                data={"tokens": 100},
            )

            # Verify result was returned
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_run_agent_with_tracking_missing_kwargs(self):
        """Test error when neither user_prompt nor message_history is provided."""
        mock_agent = MagicMock(spec=pydantic_ai.Agent)

        with pytest.raises(ValueError, match="Either 'user_prompt' or 'message_history' must be provided"):
            await run_agent_with_tracking(agent=mock_agent, chat_id="123", session_id="session123", run_kwargs={})

    @pytest.mark.asyncio
    async def test_run_agent_with_tracking_logs_error(self):
        """Test that tracking errors are logged but don't fail the function."""
        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_agent.run = AsyncMock()

        # Mock result
        mock_result = MagicMock()
        mock_result.usage.return_value = {"tokens": 100}
        mock_agent.run.return_value = mock_result

        # Mock database to raise an error
        with (
            patch("areyouok_telegram.llms.utils.async_database") as mock_db,
            patch.object(logfire, "exception") as mock_log,
        ):
            mock_db.side_effect = Exception("Database error")

            result = await run_agent_with_tracking(
                agent=mock_agent, chat_id="123", session_id="session123", run_kwargs={"user_prompt": "test"}
            )

            # Verify error was logged
            mock_log.assert_called_once()
            log_call = mock_log.call_args
            assert "Failed to log LLM usage" in log_call[0][0]
            assert log_call.kwargs["agent"] == "test_agent"
            assert log_call.kwargs["chat_id"] == "123"
            assert log_call.kwargs["session_id"] == "session123"

        # Verify result was still returned
        assert result == mock_result
