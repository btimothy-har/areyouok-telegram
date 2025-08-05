from unittest.mock import MagicMock

import pytest

from areyouok_telegram.data import LLMUsage


@pytest.mark.asyncio
async def test_track_pydantic_usage(async_database_connection):
    """Test tracking pydantic AI usage."""
    # Mock the execute result
    async_database_connection.execute.return_value.rowcount = 1

    # Mock agent and usage data
    mock_agent = MagicMock()
    mock_agent.name = "test_agent"
    mock_agent.model.model_name = "anthropic/claude-3-opus"

    mock_usage = MagicMock()
    mock_usage.request_tokens = 100
    mock_usage.response_tokens = 200

    # Track usage
    result = await LLMUsage.track_pydantic_usage(
        db_conn=async_database_connection,
        chat_id="test_chat_123",
        session_id="test_session_456",
        agent=mock_agent,
        data=mock_usage,
    )

    assert result == 1  # One row inserted

    # Verify the correct SQL was executed
    async_database_connection.execute.assert_called_once()


@pytest.mark.asyncio
async def test_track_pydantic_usage_fallback_model(async_database_connection):
    """Test tracking pydantic AI usage with fallback model."""
    # Mock the execute result
    async_database_connection.execute.return_value.rowcount = 1

    # Mock agent with fallback model
    mock_agent = MagicMock()
    mock_agent.name = "test_agent"
    mock_agent.model.model_name = "fallback:anthropic/claude-3-opus"

    # Mock the first model in the fallback list
    mock_first_model = MagicMock()
    mock_first_model.model_name = "anthropic/claude-3-opus"
    mock_agent.model.models = [mock_first_model]

    mock_usage = MagicMock()
    mock_usage.request_tokens = 100
    mock_usage.response_tokens = 200

    # Track usage
    result = await LLMUsage.track_pydantic_usage(
        db_conn=async_database_connection,
        chat_id="test_chat_fallback",
        session_id="test_session_fallback",
        agent=mock_agent,
        data=mock_usage,
    )

    assert result == 1  # One row inserted
    async_database_connection.execute.assert_called_once()


@pytest.mark.asyncio
async def test_track_pydantic_usage_model_without_provider(async_database_connection):
    """Test tracking pydantic AI usage when model name lacks provider prefix."""
    # Mock the execute result
    async_database_connection.execute.return_value.rowcount = 1

    # Mock agent with model lacking provider prefix
    mock_agent = MagicMock()
    mock_agent.name = "test_agent"
    mock_agent.model.model_name = "gpt-4"
    mock_agent.model.system = "openai"

    mock_usage = MagicMock()
    mock_usage.request_tokens = 150
    mock_usage.response_tokens = 250

    # Track usage
    result = await LLMUsage.track_pydantic_usage(
        db_conn=async_database_connection,
        chat_id="test_chat_no_provider",
        session_id="test_session_no_provider",
        agent=mock_agent,
        data=mock_usage,
    )

    assert result == 1  # One row inserted
    async_database_connection.execute.assert_called_once()


@pytest.mark.asyncio
async def test_track_usage_error_handling(async_database_connection):
    """Test that tracking errors don't break application flow."""
    # Mock the database to throw an error
    async_database_connection.execute.side_effect = Exception("Database error")

    # Mock agent with valid structure
    mock_agent = MagicMock()
    mock_agent.name = "test_agent"
    mock_agent.model.model_name = "anthropic/claude-3-opus"

    mock_usage = MagicMock()
    mock_usage.request_tokens = 100
    mock_usage.response_tokens = 200

    # This should not raise an exception
    result = await LLMUsage.track_pydantic_usage(
        db_conn=async_database_connection,
        chat_id="test_chat_error",
        session_id="test_session_error",
        agent=mock_agent,
        data=mock_usage,
    )

    assert result == 0  # Failed to insert due to database error
