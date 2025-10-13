"""Tests for LLMUsage model."""

from unittest.mock import MagicMock, patch

import pydantic_ai
import pytest

from areyouok_telegram.data.models.llm_usage import LLMUsage


class TestLLMUsage:
    """Test LLMUsage model."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_usage.calc_price")
    async def test_track_pydantic_usage_simple_model(self, mock_calc_price, mock_db_session):
        """Test tracking usage for a simple model name."""
        # Mock price calculation result
        mock_price_data = MagicMock()
        mock_price_data.input_price = 0.002
        mock_price_data.output_price = 0.006
        mock_price_data.total_price = 0.008
        mock_calc_price.return_value = mock_price_data

        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_model = MagicMock()
        mock_model.model_name = "gpt-4"
        mock_model.system = "openai"
        mock_agent.model = mock_model

        # Mock usage data
        mock_usage = MagicMock(spec=pydantic_ai.usage.RunUsage)
        mock_usage.request_tokens = 100
        mock_usage.response_tokens = 50
        mock_usage.details = None

        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_pydantic_usage(
            mock_db_session, chat_id="123", session_id="session_456", agent=mock_agent, data=mock_usage, runtime=100
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

        # Verify the statement is for llm_usage table
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "table")
        assert call_args.table.name == "llm_usage"

        # Verify cost calculation was called correctly
        mock_calc_price.assert_called_once()
        call_args = mock_calc_price.call_args
        assert call_args[1]["model_ref"] == "gpt-4"  # Just model name, not provider/model
        assert call_args[1]["provider_id"] == "openai"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_usage.calc_price")
    async def test_track_pydantic_usage_with_provider_prefix(self, mock_calc_price, mock_db_session):
        """Test tracking usage for model with provider prefix."""
        # Mock price calculation result
        mock_price_data = MagicMock()
        mock_price_data.input_price = 0.004
        mock_price_data.output_price = 0.012
        mock_price_data.total_price = 0.016
        mock_calc_price.return_value = mock_price_data

        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_model = MagicMock()
        mock_model.model_name = "anthropic/claude-3"
        mock_model.system = "anthropic"
        mock_agent.model = mock_model

        # Mock usage data
        mock_usage = MagicMock(spec=pydantic_ai.usage.RunUsage)
        mock_usage.request_tokens = 200
        mock_usage.response_tokens = 100
        mock_usage.details = None

        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_pydantic_usage(
            mock_db_session, chat_id="456", session_id="session_789", agent=mock_agent, data=mock_usage, runtime=100
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

        # Verify cost calculation was called with correct model name (should use as-is since it has provider prefix)
        mock_calc_price.assert_called_once()
        call_args = mock_calc_price.call_args
        assert call_args[1]["model_ref"] == "claude-3"  # Just model name, not provider/model
        assert call_args[1]["provider_id"] == "anthropic"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_usage.calc_price")
    @patch("areyouok_telegram.data.models.llm_usage.logfire")
    async def test_track_pydantic_usage_cost_calculation_failure(self, mock_logfire, mock_calc_price, mock_db_session):
        """Test tracking usage when cost calculation fails."""
        # Mock calc_price to raise an exception
        mock_calc_price.side_effect = Exception("API error")

        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_model = MagicMock()
        mock_model.model_name = "gpt-4"
        mock_model.system = "openai"
        mock_agent.model = mock_model

        # Mock usage data
        mock_usage = MagicMock(spec=pydantic_ai.usage.RunUsage)
        mock_usage.request_tokens = 100
        mock_usage.response_tokens = 50
        mock_usage.details = None

        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_pydantic_usage(
            mock_db_session, chat_id="123", session_id="session_456", agent=mock_agent, data=mock_usage, runtime=100
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

        # Verify that a warning was logged when cost calculation failed
        mock_logfire.warn.assert_called_once()
        warn_call_args = mock_logfire.warn.call_args[0][0]
        assert "Failed to calculate costs for model gpt-4" in warn_call_args

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_usage.calc_price")
    async def test_track_pydantic_usage_fallback_model(self, mock_calc_price, mock_db_session):
        """Test tracking usage for fallback model configuration."""
        # Mock price calculation result
        mock_price_data = MagicMock()
        mock_price_data.input_price = 0.003
        mock_price_data.output_price = 0.009
        mock_price_data.total_price = 0.012
        mock_calc_price.return_value = mock_price_data

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
        mock_usage = MagicMock(spec=pydantic_ai.usage.RunUsage)
        mock_usage.request_tokens = 150
        mock_usage.response_tokens = 75
        mock_usage.details = None

        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_pydantic_usage(
            mock_db_session, chat_id="789", session_id="session_012", agent=mock_agent, data=mock_usage, runtime=100
        )

        assert result == 1
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_usage.calc_price")
    async def test_track_pydantic_usage_exception_handling(self, mock_calc_price, mock_db_session):
        """Test exception propagation during usage tracking."""
        # Mock price calculation result (won't be used due to DB exception)
        mock_price_data = MagicMock()
        mock_price_data.input_price = 0.001
        mock_price_data.output_price = 0.002
        mock_price_data.total_price = 0.003
        mock_calc_price.return_value = mock_price_data

        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_model = MagicMock()
        mock_model.model_name = "test-model"
        mock_model.system = "test"
        mock_agent.model = mock_model

        # Mock usage data
        mock_usage = MagicMock(spec=pydantic_ai.usage.RunUsage)
        mock_usage.request_tokens = 100
        mock_usage.response_tokens = 50
        mock_usage.details = None

        # Mock execute to raise an exception
        mock_db_session.execute.side_effect = Exception("Database error")

        # The method should propagate exceptions
        with pytest.raises(Exception, match="Database error"):
            await LLMUsage.track_pydantic_usage(
                mock_db_session, chat_id="999", session_id="session_999", agent=mock_agent, data=mock_usage, runtime=100
            )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_usage.calc_price")
    async def test_track_pydantic_usage_zero_tokens(self, mock_calc_price, mock_db_session):
        """Test tracking usage with zero tokens."""
        # Mock price calculation result for zero tokens
        mock_price_data = MagicMock()
        mock_price_data.input_price = 0.0
        mock_price_data.output_price = 0.0
        mock_price_data.total_price = 0.0
        mock_calc_price.return_value = mock_price_data

        # Mock agent
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test_agent"
        mock_model = MagicMock()
        mock_model.model_name = "test-model"
        mock_model.system = "test"
        mock_agent.model = mock_model

        # Mock usage data with zero tokens
        mock_usage = MagicMock(spec=pydantic_ai.usage.RunUsage)
        mock_usage.request_tokens = 0
        mock_usage.response_tokens = 0
        mock_usage.details = None

        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result

        result = await LLMUsage.track_pydantic_usage(
            mock_db_session, chat_id="000", session_id="session_000", agent=mock_agent, data=mock_usage, runtime=100
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
        """Test exception propagation in track_generic_usage."""
        # Mock execute to raise an exception
        mock_db_session.execute.side_effect = Exception("Database connection error")

        # The method should propagate exceptions
        with pytest.raises(Exception, match="Database connection error"):
            await LLMUsage.track_generic_usage(
                mock_db_session,
                chat_id="error_test",
                session_id="error_session",
                usage_type="error.test",
                model="error/model",
                provider="error",
                input_tokens=10,
                output_tokens=5,
            )

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
