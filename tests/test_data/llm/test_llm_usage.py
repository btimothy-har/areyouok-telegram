"""Tests for LLMUsage model."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from areyouok_telegram.data.models import LLMUsage


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_llm_usage_save(mock_db_session):
    """Test LLMUsage.save() inserts and returns with id."""
    usage = LLMUsage(
        chat_id=1,
        session_id=2,
        timestamp=datetime.now(UTC),
        usage_type="pydantic.test_agent",
        model="gpt-4",
        provider="openai",
        input_tokens=100,
        output_tokens=50,
        runtime=1.5,
    )

    class Row:
        id = 10
        chat_id = 1
        session_id = 2
        timestamp = usage.timestamp
        usage_type = "pydantic.test_agent"
        model = "gpt-4"
        provider = "openai"
        input_tokens = 100
        output_tokens = 50
        runtime = 1.5
        details = None
        input_cost = None
        output_cost = None
        total_cost = None

    class _ResOne:
        def scalar_one(self):
            return Row()

    mock_db_session.execute.return_value = _ResOne()
    saved = await usage.save()
    assert saved.id == 10


def test_llm_usage_calculate_costs_success():
    """Test LLMUsage.calculate_costs() with successful pricing."""
    with patch("areyouok_telegram.data.models.llm.llm_usage.calc_price") as mock_calc:
        mock_price = MagicMock()
        mock_price.input_price = 0.001
        mock_price.output_price = 0.002
        mock_price.total_price = 0.003
        mock_calc.return_value = mock_price

        input_cost, output_cost, total_cost = LLMUsage.calculate_costs(
            model_name="gpt-4", provider="openai", input_tokens=100, output_tokens=50
        )

        assert input_cost == 0.001
        assert output_cost == 0.002
        assert total_cost == 0.003


def test_llm_usage_calculate_costs_failure():
    """Test LLMUsage.calculate_costs() handles exceptions gracefully."""
    with patch("areyouok_telegram.data.models.llm.llm_usage.calc_price", side_effect=Exception("Pricing API down")):
        with patch("areyouok_telegram.data.models.llm.llm_usage.logfire.warn") as mock_warn:
            input_cost, output_cost, total_cost = LLMUsage.calculate_costs(
                model_name="unknown-model", provider="unknown", input_tokens=10, output_tokens=5
            )

            assert input_cost is None and output_cost is None and total_cost is None
            mock_warn.assert_called_once()
