"""Tests for database connection module."""

import pytest

from areyouok_telegram.data.connection import async_database


class TestAsyncDatabase:
    """Test async_database context manager."""

    @pytest.mark.asyncio
    async def test_successful_transaction(self, mock_db_session):
        """Test successful database transaction commits."""
        async with async_database() as session:
            assert session == mock_db_session
            # Simulate some database operation
            await session.execute("SELECT 1")

        # Verify commit was called on successful exit
        mock_db_session.commit.assert_called_once()
        mock_db_session.rollback.assert_not_called()
        mock_db_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_exception(self, mock_db_session):
        """Test database rollback on exception."""
        with pytest.raises(ValueError, match="Test"):
            async with async_database() as session:
                assert session == mock_db_session
                raise ValueError("Test")

        # Verify rollback was called on exception
        mock_db_session.commit.assert_not_called()
        mock_db_session.rollback.assert_called_once()
        mock_db_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_closed_after_commit(self, mock_db_session):
        """Test session is closed after successful commit."""
        async with async_database():
            pass

        # Verify both commit and close were called
        mock_db_session.commit.assert_called_once()
        mock_db_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_closed_after_rollback(self, mock_db_session):
        """Test session is closed even after rollback."""
        with pytest.raises(RuntimeError, match="Test"):
            async with async_database():
                raise RuntimeError("Test")

        # Verify both rollback and close were called
        mock_db_session.rollback.assert_called_once()
        mock_db_session.close.assert_called_once()
