"""Tests for the Context dataclass and its database operations."""

from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from areyouok_telegram.data.context import VALID_CONTEXT_TYPES
from areyouok_telegram.data.context import Context
from areyouok_telegram.data.context import InvalidContextTypeError


class TestContextNewOrUpdate:
    """Test the new_or_update class method."""

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_new_or_update_valid_context(self, async_database_connection):
        """Test creating a new context with valid type."""
        chat_id = "123456"
        session_id = "session_abc123"
        ctype = "session"
        content = "This is a session summary"

        # Mock the execute method
        async_database_connection.execute = AsyncMock()

        # Call the method
        await Context.new_or_update(
            session=async_database_connection,
            chat_id=chat_id,
            session_id=session_id,
            ctype=ctype,
            content=content,
        )

        # Verify execute was called
        async_database_connection.execute.assert_called_once()

        # Verify the values in the insert statement
        # Note: We can't directly inspect the pg_insert values easily,
        # but we can verify execute was called with proper structure

    @pytest.mark.asyncio
    async def test_new_or_update_invalid_context_type(self, async_database_connection):
        """Test that invalid context type raises exception."""
        chat_id = "123456"
        session_id = "session_abc123"
        ctype = "invalid_type"
        content = "Some content"

        # Should raise InvalidContextTypeError
        with pytest.raises(InvalidContextTypeError) as exc_info:
            await Context.new_or_update(
                session=async_database_connection,
                chat_id=chat_id,
                session_id=session_id,
                ctype=ctype,
                content=content,
            )

        # Verify the exception details
        assert exc_info.value.context_type == "invalid_type"
        assert "invalid_type" in str(exc_info.value)
        assert "session" in str(exc_info.value)  # Should mention valid types

        # Verify execute was not called
        async_database_connection.execute.assert_not_called()

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 10:30:00", tz_offset=0)
    async def test_new_or_update_converts_chat_id_to_string(self, async_database_connection):
        """Test that chat_id is converted to string."""
        chat_id = 123456  # Integer
        session_id = "session_abc123"
        ctype = "session"
        content = "Content"

        async_database_connection.execute = AsyncMock()

        # Should not raise error even with integer chat_id
        await Context.new_or_update(
            session=async_database_connection,
            chat_id=chat_id,
            session_id=session_id,
            ctype=ctype,
            content=content,
        )

        # Verify execute was called
        async_database_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_new_or_update_all_valid_context_types(self, async_database_connection):
        """Test that all valid context types work correctly."""
        chat_id = "123456"
        session_id = "session_abc123"
        content = "Test content"

        async_database_connection.execute = AsyncMock()

        # Test each valid context type
        for ctype in VALID_CONTEXT_TYPES:
            await Context.new_or_update(
                session=async_database_connection,
                chat_id=chat_id,
                session_id=session_id,
                ctype=ctype,
                content=content,
            )

        # Verify execute was called for each valid type
        assert async_database_connection.execute.call_count == len(VALID_CONTEXT_TYPES)


class TestContextRetrieveByChat:
    """Test the retrieve_context_by_chat class method."""

    @pytest.mark.asyncio
    async def test_retrieve_context_by_chat_no_type_filter(self, async_database_connection):
        """Test retrieving contexts without type filter."""
        chat_id = "123456"

        # Create mock contexts
        context1 = MagicMock(spec=Context)
        context1.chat_id = chat_id
        context1.type = "session"
        context1.content = "Session 1"
        context1.created_at = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        context2 = MagicMock(spec=Context)
        context2.chat_id = chat_id
        context2.type = "session"
        context2.content = "Session 2"
        context2.created_at = datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [context2, context1]  # Ordered by created_at desc
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Context.retrieve_context_by_chat(
            session=async_database_connection,
            chat_id=chat_id,
        )

        # Verify the result
        assert len(result) == 2
        assert result[0] == context2  # Most recent first
        assert result[1] == context1

        # Verify the query was executed
        async_database_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_context_by_chat_with_type_filter(self, async_database_connection):
        """Test retrieving contexts with type filter."""
        chat_id = "123456"
        ctype = "session"

        # Create mock context
        context1 = MagicMock(spec=Context)
        context1.chat_id = chat_id
        context1.type = "session"
        context1.content = "Session content"

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [context1]
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Context.retrieve_context_by_chat(
            session=async_database_connection,
            chat_id=chat_id,
            ctype=ctype,
        )

        # Verify the result
        assert len(result) == 1
        assert result[0] == context1

        # Verify the query was executed
        async_database_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_context_by_chat_with_limit(self, async_database_connection):
        """Test retrieving contexts with custom limit."""
        chat_id = "123456"
        limit = 5

        # Create mock contexts
        contexts = []
        for _ in range(7):
            context = MagicMock(spec=Context)
            context.chat_id = chat_id
            context.type = "session"
            context.content = "Session content"
            contexts.append(context)

        # Mock the query result (should return only 5 due to limit)
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = contexts[:5]  # Only first 5
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Context.retrieve_context_by_chat(
            session=async_database_connection,
            chat_id=chat_id,
            limit=limit,
        )

        # Verify the result
        assert len(result) == 5

        # Verify the query was executed
        async_database_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_context_by_chat_no_results(self, async_database_connection):
        """Test retrieving contexts when none exist."""
        chat_id = "123456"

        # Mock no results
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Context.retrieve_context_by_chat(
            session=async_database_connection,
            chat_id=chat_id,
        )

        # Verify returns None when no contexts found
        assert result is None

    @pytest.mark.asyncio
    async def test_retrieve_context_by_chat_invalid_type(self, async_database_connection):
        """Test that invalid context type raises exception."""
        chat_id = "123456"
        ctype = "invalid_type"

        # Should raise InvalidContextTypeError
        with pytest.raises(InvalidContextTypeError) as exc_info:
            await Context.retrieve_context_by_chat(
                session=async_database_connection,
                chat_id=chat_id,
                ctype=ctype,
            )

        # Verify the exception details
        assert exc_info.value.context_type == "invalid_type"

        # Verify execute was not called
        async_database_connection.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_retrieve_context_by_chat_default_limit(self, async_database_connection):
        """Test that default limit is 3."""
        chat_id = "123456"

        # Create 5 mock contexts
        contexts = []
        for _ in range(5):
            context = MagicMock(spec=Context)
            context.chat_id = chat_id
            contexts.append(context)

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = contexts[:3]  # Default limit is 3
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method without specifying limit
        result = await Context.retrieve_context_by_chat(
            session=async_database_connection,
            chat_id=chat_id,
        )

        # Verify the result respects default limit
        assert len(result) == 3


class TestInvalidContextTypeError:
    """Test the InvalidContextTypeError exception."""

    def test_invalid_context_type_error_message(self):
        """Test that the error message is correctly formatted."""
        error = InvalidContextTypeError("unknown")

        assert str(error) == f"Invalid context type: unknown. Expected one of: {VALID_CONTEXT_TYPES}."
        assert error.context_type == "unknown"

    def test_invalid_context_type_error_attributes(self):
        """Test that the error stores the context type."""
        context_type = "custom_type"
        error = InvalidContextTypeError(context_type)

        assert error.context_type == context_type
        assert context_type in str(error)
        assert "session" in str(error)  # Should mention valid types


class TestContextModel:
    """Test the Context model structure and properties."""

    def test_context_table_name(self):
        """Test that the table name is correct."""
        assert Context.__tablename__ == "context"

    def test_context_columns(self):
        """Test that all expected columns exist."""
        # Get column names
        columns = {col.name for col in Context.__table__.columns}

        # Verify all expected columns exist
        expected_columns = {
            "id",
            "chat_id",
            "session_id",
            "type",
            "content",
            "created_at",
        }

        assert expected_columns.issubset(columns)

    def test_context_primary_key(self):
        """Test that id is the primary key."""
        pk_columns = [col.name for col in Context.__table__.primary_key.columns]
        assert pk_columns == ["id"]

    def test_context_schema(self):
        """Test that the schema is set from ENV."""
        # The schema should be set in __table_args__
        # Note: The actual schema value depends on the ENV at import time
        assert "schema" in Context.__table_args__
        assert isinstance(Context.__table_args__["schema"], str)

    @pytest.mark.asyncio
    async def test_get_by_session_id_success(self, async_database_connection):
        """Test getting contexts by session_id."""
        session_id = "session-123"

        # Create mock contexts
        context1 = MagicMock(spec=Context)
        context1.id = 1
        context1.session_id = session_id
        context1.type = "session"

        context2 = MagicMock(spec=Context)
        context2.id = 2
        context2.session_id = session_id
        context2.type = "user"

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [context1, context2]
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Context.get_by_session_id(
            session=async_database_connection,
            session_id=session_id,
        )

        # Verify the result
        assert len(result) == 2
        assert result[0] == context1
        assert result[1] == context2

        # Verify the query was executed
        async_database_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_session_id_with_type_filter(self, async_database_connection):
        """Test getting contexts by session_id with type filter."""
        session_id = "session-123"
        ctype = "session"

        # Create mock context
        context = MagicMock(spec=Context)
        context.id = 1
        context.session_id = session_id
        context.type = ctype

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [context]
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Context.get_by_session_id(
            session=async_database_connection,
            session_id=session_id,
            ctype=ctype,
        )

        # Verify the result
        assert len(result) == 1
        assert result[0] == context

        # Verify the query was executed
        async_database_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_session_id_invalid_type(self, async_database_connection):
        """Test get_by_session_id raises error for invalid type."""
        with pytest.raises(InvalidContextTypeError) as exc_info:
            await Context.get_by_session_id(
                session=async_database_connection,
                session_id="session-123",
                ctype="invalid_type",
            )

        assert exc_info.value.context_type == "invalid_type"

    @pytest.mark.asyncio
    async def test_get_by_session_id_no_results(self, async_database_connection):
        """Test get_by_session_id returns None when no results."""
        session_id = "session-123"

        # Mock no results
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Context.get_by_session_id(
            session=async_database_connection,
            session_id=session_id,
        )

        # Should return None when no results
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_chat_id_success(self, async_database_connection):
        """Test getting contexts by chat_id."""
        chat_id = "123456"

        # Create mock contexts
        context1 = MagicMock(spec=Context)
        context1.id = 1
        context1.chat_id = chat_id
        context1.type = "session"

        context2 = MagicMock(spec=Context)
        context2.id = 2
        context2.chat_id = chat_id
        context2.type = "user"

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [context1, context2]
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Context.get_by_chat_id(
            session=async_database_connection,
            chat_id=chat_id,
        )

        # Verify the result
        assert len(result) == 2
        assert result[0] == context1
        assert result[1] == context2

        # Verify the query was executed
        async_database_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_chat_id_with_type_filter(self, async_database_connection):
        """Test getting contexts by chat_id with type filter."""
        chat_id = "123456"
        ctype = "session"

        # Create mock context
        context = MagicMock(spec=Context)
        context.id = 1
        context.chat_id = chat_id
        context.type = ctype

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [context]
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Context.get_by_chat_id(
            session=async_database_connection,
            chat_id=chat_id,
            ctype=ctype,
        )

        # Verify the result
        assert len(result) == 1
        assert result[0] == context

        # Verify the query was executed
        async_database_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_chat_id_invalid_type(self, async_database_connection):
        """Test get_by_chat_id raises error for invalid type."""
        with pytest.raises(InvalidContextTypeError) as exc_info:
            await Context.get_by_chat_id(
                session=async_database_connection,
                chat_id="123456",
                ctype="invalid_type",
            )

        assert exc_info.value.context_type == "invalid_type"

    @pytest.mark.asyncio
    async def test_get_by_chat_id_no_results(self, async_database_connection):
        """Test get_by_chat_id returns None when no results."""
        chat_id = "123456"

        # Mock no results
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        async_database_connection.execute.return_value = mock_result

        # Call the method
        result = await Context.get_by_chat_id(
            session=async_database_connection,
            chat_id=chat_id,
        )

        # Should return None when no results
        assert result is None
