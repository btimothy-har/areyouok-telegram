"""Test module for LLM utilities."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import anthropic
import google.genai.errors
import httpx
import openai
import pydantic_ai
import pytest

from areyouok_telegram.llms.utils import run_agent_with_tracking
from areyouok_telegram.llms.utils import should_retry_llm_error


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


class TestShouldRetryLLMError:
    """Test the should_retry_llm_error function."""

    def test_httpx_network_error_should_retry(self):
        """Test that httpx.NetworkError triggers retry."""
        error = httpx.NetworkError("Connection failed")
        assert should_retry_llm_error(error) is True

    def test_httpx_connect_error_should_retry(self):
        """Test that httpx.ConnectError (subclass of NetworkError) triggers retry."""
        error = httpx.ConnectError("DNS resolution failed")
        assert should_retry_llm_error(error) is True

    def test_httpx_timeout_exception_should_retry(self):
        """Test that httpx.TimeoutException triggers retry."""
        error = httpx.TimeoutException("Request timed out")
        assert should_retry_llm_error(error) is True

    def test_httpx_connect_timeout_should_retry(self):
        """Test that httpx.ConnectTimeout (subclass of TimeoutException) triggers retry."""
        error = httpx.ConnectTimeout("Connection timeout")
        assert should_retry_llm_error(error) is True

    def test_httpx_read_timeout_should_retry(self):
        """Test that httpx.ReadTimeout (subclass of TimeoutException) triggers retry."""
        error = httpx.ReadTimeout("Read timeout")
        assert should_retry_llm_error(error) is True

    def test_httpx_write_timeout_should_retry(self):
        """Test that httpx.WriteTimeout (subclass of TimeoutException) triggers retry."""
        error = httpx.WriteTimeout("Write timeout")
        assert should_retry_llm_error(error) is True

    def test_httpx_read_error_should_retry(self):
        """Test that httpx.ReadError (subclass of NetworkError) triggers retry."""
        error = httpx.ReadError("Read error")
        assert should_retry_llm_error(error) is True

    def test_httpx_write_error_should_retry(self):
        """Test that httpx.WriteError (subclass of NetworkError) triggers retry."""
        error = httpx.WriteError("Write error")
        assert should_retry_llm_error(error) is True

    def test_anthropic_timeout_error_should_retry(self):
        """Test that Anthropic API timeout errors trigger retry."""
        error = anthropic.APITimeoutError(request=MagicMock())
        assert should_retry_llm_error(error) is True

    def test_anthropic_5xx_error_should_retry(self):
        """Test that Anthropic 5xx errors trigger retry."""
        error = anthropic.APIStatusError(message="Server error", response=MagicMock(), body={"error": "Server error"})
        error.status_code = 500
        assert should_retry_llm_error(error) is True

    def test_anthropic_4xx_error_should_not_retry(self):
        """Test that Anthropic 4xx errors do not trigger retry."""
        error = anthropic.APIStatusError(message="Client error", response=MagicMock(), body={"error": "Client error"})
        error.status_code = 400
        assert should_retry_llm_error(error) is False

    def test_openai_timeout_error_should_retry(self):
        """Test that OpenAI API timeout errors trigger retry."""
        error = openai.APITimeoutError(request=MagicMock())
        assert should_retry_llm_error(error) is True

    def test_openai_5xx_error_should_retry(self):
        """Test that OpenAI 5xx errors trigger retry."""
        response = MagicMock()
        response.status_code = 500
        response.request = MagicMock()
        error = openai.APIStatusError(message="Server error", response=response, body={"error": "Server error"})
        assert should_retry_llm_error(error) is True

    def test_openai_4xx_error_should_not_retry(self):
        """Test that OpenAI 4xx errors do not trigger retry."""
        response = MagicMock()
        response.status_code = 400
        response.request = MagicMock()
        error = openai.APIStatusError(message="Client error", response=response, body={"error": "Client error"})
        assert should_retry_llm_error(error) is False

    def test_google_server_error_should_retry(self):
        """Test that Google GenAI server errors trigger retry."""
        error = google.genai.errors.ServerError("Server error", response_json={})
        assert should_retry_llm_error(error) is True

    def test_non_retryable_error_should_not_retry(self):
        """Test that non-retryable errors do not trigger retry."""
        error = ValueError("Invalid input")
        assert should_retry_llm_error(error) is False

    def test_httpx_protocol_error_should_not_retry(self):
        """Test that httpx.ProtocolError does not trigger retry (not transient)."""
        error = httpx.ProtocolError("Protocol violation")
        assert should_retry_llm_error(error) is False

    def test_httpx_proxy_error_should_not_retry(self):
        """Test that httpx.ProxyError does not trigger retry (configuration issue)."""
        error = httpx.ProxyError("Proxy configuration error")
        assert should_retry_llm_error(error) is False
