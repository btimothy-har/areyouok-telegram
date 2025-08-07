"""Tests for LLMUsage model."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pydantic_ai
import pytest

from areyouok_telegram.data.models.llm_usage import LLMUsage


class TestLLMUsage:
    """Test LLMUsage model."""

    @pytest.mark.asyncio
    async def test_track_pydantic_usage_simple_model(self, mock_db_session):
        """Test tracking usage for a simple model name."""
        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_model = MagicMock()
        mock_model.model_name = "gpt-4"
        mock_model.system = "openai"
        mock_agent.model = mock_model

        # Mock usage data
        mock_usage = MagicMock(spec=pydantic_ai.usage.Usage)
        mock_usage.request_tokens = 100
        mock_usage.response_tokens = 50

        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_pydantic_usage(
            mock_db_session, chat_id="123", session_id="session_456", agent=mock_agent, data=mock_usage
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

        # Verify the statement is for llm_usage table
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "table")
        assert call_args.table.name == "llm_usage"

    @pytest.mark.asyncio
    async def test_track_pydantic_usage_with_provider_prefix(self, mock_db_session):
        """Test tracking usage for model with provider prefix."""
        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_model = MagicMock()
        mock_model.model_name = "anthropic/claude-3"
        mock_model.system = "anthropic"
        mock_agent.model = mock_model

        # Mock usage data
        mock_usage = MagicMock(spec=pydantic_ai.usage.Usage)
        mock_usage.request_tokens = 200
        mock_usage.response_tokens = 100

        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_pydantic_usage(
            mock_db_session, chat_id="456", session_id="session_789", agent=mock_agent, data=mock_usage
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_track_pydantic_usage_fallback_model(self, mock_db_session):
        """Test tracking usage for fallback model configuration."""
        # Mock agent with fallback model
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"

        # Mock fallback model structure
        mock_primary_model = MagicMock()
        mock_primary_model.model_name = "primary/model"
        mock_primary_model.system = "primary"

        mock_fallback_model = MagicMock()
        mock_fallback_model.model_name = "fallback:primary"
        mock_fallback_model.models = [mock_primary_model]

        mock_agent.model = mock_fallback_model

        # Mock usage data
        mock_usage = MagicMock(spec=pydantic_ai.usage.Usage)
        mock_usage.request_tokens = 150
        mock_usage.response_tokens = 75

        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_pydantic_usage(
            mock_db_session, chat_id="789", session_id="session_012", agent=mock_agent, data=mock_usage
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_track_pydantic_usage_exception_handling(self, mock_db_session):
        """Test exception handling during usage tracking."""
        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_model = MagicMock()
        mock_model.model_name = "test-model"
        mock_model.system = "test"
        mock_agent.model = mock_model

        # Mock usage data
        mock_usage = MagicMock(spec=pydantic_ai.usage.Usage)
        mock_usage.request_tokens = 100
        mock_usage.response_tokens = 50

        # Mock execute to raise an exception
        mock_db_session.execute.side_effect = Exception("Database error")

        # Mock logfire to verify exception logging
        with patch("areyouok_telegram.data.models.llm_usage.logfire") as mock_logfire:
            result = await LLMUsage.track_pydantic_usage(
                mock_db_session, chat_id="999", session_id="session_999", agent=mock_agent, data=mock_usage
            )

            assert result == 0
            mock_logfire.exception.assert_called_once()
            assert "Failed to insert pydantic usage record" in str(mock_logfire.exception.call_args)

    @pytest.mark.asyncio
    async def test_track_pydantic_usage_zero_tokens(self, mock_db_session):
        """Test tracking usage with zero tokens."""
        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_model = MagicMock()
        mock_model.model_name = "test-model"
        mock_model.system = "test"
        mock_agent.model = mock_model

        # Mock usage data with zero tokens
        mock_usage = MagicMock(spec=pydantic_ai.usage.Usage)
        mock_usage.request_tokens = 0
        mock_usage.response_tokens = 0

        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_pydantic_usage(
            mock_db_session, chat_id="000", session_id="session_000", agent=mock_agent, data=mock_usage
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()
