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

    @pytest.mark.asyncio
    async def test_track_generic_usage_all_params(self, mock_db_session):
        """Test track_generic_usage with all parameters provided."""
        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_generic_usage(
            mock_db_session,
            chat_id="123",
            session_id="session_456",
            usage_type="custom.agent",
            model="custom/model",
            provider="custom",
            input_tokens=100,
            output_tokens=50,
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

        # Verify the statement is for llm_usage table
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "table")
        assert call_args.table.name == "llm_usage"

    @pytest.mark.asyncio
    async def test_track_generic_usage_minimal_params(self, mock_db_session):
        """Test track_generic_usage with minimal parameters (defaults)."""
        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        # Must provide all parameters that the @traced decorator expects
        result = await LLMUsage.track_generic_usage(
            mock_db_session,
            chat_id="test",
            session_id="session_test",
            usage_type="test.minimal",
            model="test/model",
            provider="test",
            input_tokens=0,
            output_tokens=0,
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

        # Verify the statement is for llm_usage table
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "table")
        assert call_args.table.name == "llm_usage"

    @pytest.mark.asyncio
    async def test_track_generic_usage_none_values(self, mock_db_session):
        """Test track_generic_usage with None values for optional parameters."""
        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_generic_usage(
            mock_db_session,
            chat_id=None,
            session_id=None,
            usage_type=None,
            model=None,
            provider=None,
            input_tokens=0,
            output_tokens=0,
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_track_generic_usage_exception_handling(self, mock_db_session):
        """Test exception handling in track_generic_usage."""
        # Mock execute to raise an exception
        mock_db_session.execute.side_effect = Exception("Database connection error")

        # Mock logfire to verify exception logging
        with patch("areyouok_telegram.data.models.llm_usage.logfire") as mock_logfire:
            result = await LLMUsage.track_generic_usage(
                mock_db_session,
                chat_id="error_test",
                session_id="error_session",
                usage_type="error.test",
                model="error/model",
                provider="error",
                input_tokens=10,
                output_tokens=5,
            )

            assert result == 0
            mock_logfire.exception.assert_called_once()
            assert "Failed to insert usage record" in str(mock_logfire.exception.call_args)

    @pytest.mark.asyncio
    async def test_track_generic_usage_large_token_counts(self, mock_db_session):
        """Test track_generic_usage with large token counts."""
        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_generic_usage(
            mock_db_session,
            chat_id="large_tokens_test",
            session_id="large_session",
            usage_type="large.test",
            model="large/model",
            provider="large",
            input_tokens=999999,
            output_tokens=888888,
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_track_generic_usage_zero_rowcount(self, mock_db_session):
        """Test track_generic_usage when no rows are affected."""
        # Mock execute result with zero rowcount
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_generic_usage(
            mock_db_session,
            chat_id="zero_rows_test",
            session_id="zero_session",
            usage_type="zero.test",
            model="zero/model",
            provider="zero",
            input_tokens=0,
            output_tokens=0,
        )

        assert result == 0
        mock_db_session.execute.assert_called_once()
