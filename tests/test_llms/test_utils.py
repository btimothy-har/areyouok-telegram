"""Test module for LLM utilities."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

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

        # Mock asyncio.create_task and properly close the coroutine
        with patch("areyouok_telegram.llms.utils.asyncio.create_task") as mock_create_task:
            # Create a mock task that properly handles the coroutine
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await run_agent_with_tracking(
                agent=mock_agent, chat_id="123", session_id="session123", run_kwargs={"message_history": []}
            )

            # Verify agent was called
            mock_agent.run.assert_called_once_with(message_history=[])

            # Verify create_task was called with tracking function
            mock_create_task.assert_called_once()

            # Close the coroutine that was passed to create_task to prevent warnings
            coro = mock_create_task.call_args[0][0]
            coro.close()

            # Verify result was returned
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_run_agent_with_tracking_missing_kwargs(self):
        """Test error when neither user_prompt nor message_history is provided."""
        mock_agent = MagicMock(spec=pydantic_ai.Agent)

        with pytest.raises(ValueError, match="Either 'user_prompt' or 'message_history' must be provided"):
            await run_agent_with_tracking(agent=mock_agent, chat_id="123", session_id="session123", run_kwargs={})

    @pytest.mark.asyncio
    async def test_run_agent_with_tracking_task_created(self):
        """Test that tracking task is created in the background."""
        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_agent.run = AsyncMock()

        # Mock result
        mock_result = MagicMock()
        mock_result.usage.return_value = {"tokens": 100}
        mock_agent.run.return_value = mock_result

        # Mock asyncio.create_task to verify it's called
        with patch("areyouok_telegram.llms.utils.asyncio.create_task") as mock_create_task:
            # Create a mock task that properly handles the coroutine
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await run_agent_with_tracking(
                agent=mock_agent, chat_id="123", session_id="session123", run_kwargs={"user_prompt": "test"}
            )

            # Verify create_task was called
            mock_create_task.assert_called_once()

            # Close the coroutine that was passed to create_task to prevent warnings
            coro = mock_create_task.call_args[0][0]
            coro.close()

            # Verify result was still returned
            assert result == mock_result
