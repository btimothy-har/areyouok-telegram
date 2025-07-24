# ruff: noqa: TRY003

"""Tests for the data utilities module."""

from unittest.mock import AsyncMock

import pytest
from asyncpg.exceptions import ConnectionDoesNotExistError
from asyncpg.exceptions import InterfaceError
from sqlalchemy.exc import DBAPIError

from areyouok_telegram.data.utils import with_retry


class TestWithRetryDecorator:
    """Test the with_retry decorator functionality."""

    async def test_success_on_first_attempt(self):
        """Test that successful functions are not retried."""
        call_count = 0

        @with_retry()
        async def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_function()

        assert result == "success"
        assert call_count == 1

    async def test_retry_on_connection_does_not_exist_error(self):
        """Test retry behavior on ConnectionDoesNotExistError."""
        call_count = 0

        @with_retry()
        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionDoesNotExistError("Connection lost")
            return "success after retries"

        result = await failing_function()

        assert result == "success after retries"
        assert call_count == 3

    async def test_retry_on_dbapi_error(self):
        """Test retry behavior on DBAPIError."""
        call_count = 0

        @with_retry()
        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise DBAPIError("Database error", None, None)
            return "success after retry"

        result = await failing_function()

        assert result == "success after retry"
        assert call_count == 2

    async def test_retry_on_interface_error(self):
        """Test retry behavior on InterfaceError."""
        call_count = 0

        @with_retry()
        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise InterfaceError("Interface error")
            return "success after retries"

        result = await failing_function()

        assert result == "success after retries"
        assert call_count == 4

    async def test_no_retry_on_other_exceptions(self):
        """Test that other exceptions are not retried."""
        call_count = 0

        @with_retry()
        async def failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("This should not be retried")

        with pytest.raises(ValueError, match="This should not be retried"):
            await failing_function()

        assert call_count == 1

    async def test_max_retry_attempts_reached(self):
        """Test that function fails after maximum retry attempts."""
        call_count = 0

        @with_retry()
        async def always_failing_function():
            nonlocal call_count
            call_count += 1
            raise ConnectionDoesNotExistError("Always fails")

        with pytest.raises(ConnectionDoesNotExistError, match="Always fails"):
            await always_failing_function()

        # Should have attempted 5 times (initial + 4 retries)
        assert call_count == 5

    async def test_decorator_preserves_function_signature(self):
        """Test that the decorator preserves the original function's signature."""

        @with_retry()
        async def function_with_args(arg1, arg2, kwarg1=None):
            return f"{arg1}-{arg2}-{kwarg1}"

        result = await function_with_args("a", "b", kwarg1="c")

        assert result == "a-b-c"

    async def test_decorator_works_with_database_session_mock(self):
        """Test decorator with a mock database session pattern."""
        mock_session = AsyncMock()
        call_count = 0

        @with_retry()
        async def database_operation(session):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise DBAPIError("Temporary database issue", None, None)
            await session.execute("SELECT 1")
            return "database operation completed"

        result = await database_operation(mock_session)

        assert result == "database operation completed"
        assert call_count == 3
        assert mock_session.execute.call_count == 1

    async def test_mixed_exception_types_in_retries(self):
        """Test that different retry-eligible exceptions work in sequence."""
        call_count = 0
        exceptions = [
            ConnectionDoesNotExistError("Connection error"),
            DBAPIError("Database error", None, None),
            InterfaceError("Interface error"),
        ]

        @with_retry()
        async def mixed_failures():
            nonlocal call_count
            if call_count < len(exceptions):
                exception = exceptions[call_count]
                call_count += 1
                raise exception
            call_count += 1
            return "success after mixed failures"

        result = await mixed_failures()

        assert result == "success after mixed failures"
        assert call_count == 4  # 3 failures + 1 success
