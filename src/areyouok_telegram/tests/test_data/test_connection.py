# ruff: noqa: TRY003

"""Tests for the database connection module."""

from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from areyouok_telegram.data import Base
from areyouok_telegram.data import async_database_session
from areyouok_telegram.data import async_engine
from areyouok_telegram.data.connection import AsyncSessionLocal


class TestAsyncDatabaseSession:
    """Test the async_database_session context manager."""

    @patch("areyouok_telegram.data.connection.AsyncSessionLocal")
    async def test_session_commit_on_success(self, mock_session_local):
        """Test that session commits when no exception occurs."""
        # Setup mock session
        mock_session = AsyncMock()
        mock_session_local.return_value = mock_session

        # Use the context manager successfully
        async with async_database_session() as session:
            # Simulate some database work
            await session.execute("SELECT 1")

        # Verify session lifecycle
        mock_session_local.assert_called_once()
        mock_session.execute.assert_called_once_with("SELECT 1")
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()
        mock_session.rollback.assert_not_called()

    @patch("areyouok_telegram.data.connection.AsyncSessionLocal")
    async def test_session_rollback_on_exception(self, mock_session_local):
        """Test that session rolls back when an exception occurs."""
        # Setup mock session
        mock_session = AsyncMock()
        mock_session_local.return_value = mock_session

        # Use the context manager with an exception
        with pytest.raises(ValueError, match="Test exception"):
            async with async_database_session() as session:
                # Simulate some database work
                await session.execute("INSERT INTO test VALUES (1)")
                # Raise an exception
                raise ValueError("Test exception")

        # Verify session lifecycle
        mock_session_local.assert_called_once()
        mock_session.execute.assert_called_once_with("INSERT INTO test VALUES (1)")
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
        mock_session.commit.assert_not_called()

    @patch("areyouok_telegram.data.connection.AsyncSessionLocal")
    async def test_session_close_always_called(self, mock_session_local):
        """Test that session.close() is always called, even on exception."""
        # Setup mock session
        mock_session = AsyncMock()
        mock_session_local.return_value = mock_session

        # Test with exception
        with pytest.raises(RuntimeError):
            async with async_database_session():
                raise RuntimeError("Database error")

        mock_session.close.assert_called_once()

        # Reset and test without exception
        mock_session.reset_mock()
        mock_session_local.reset_mock()

        async with async_database_session():
            pass

        mock_session.close.assert_called_once()

    @patch("areyouok_telegram.data.connection.AsyncSessionLocal")
    async def test_session_rollback_exception_handling(self, mock_session_local):
        """Test that rollback exceptions are raised when they occur."""
        # Setup mock session with rollback that raises an exception
        mock_session = AsyncMock()
        mock_session.rollback.side_effect = Exception("Rollback failed")
        mock_session_local.return_value = mock_session

        # When rollback fails, that exception should be raised
        with pytest.raises(Exception, match="Rollback failed"):
            async with async_database_session():
                raise ValueError("Original error")

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("areyouok_telegram.data.connection.AsyncSessionLocal")
    async def test_session_commit_exception_handling(self, mock_session_local):
        """Test behavior when commit fails."""
        # Setup mock session with commit that raises an exception
        mock_session = AsyncMock()
        mock_session.commit.side_effect = Exception("Commit failed")
        mock_session_local.return_value = mock_session

        # Commit exception should be raised
        with pytest.raises(Exception, match="Commit failed"):
            async with async_database_session():
                pass

        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()
        mock_session.rollback.assert_not_called()

    @patch("areyouok_telegram.data.connection.AsyncSessionLocal")
    async def test_multiple_operations_in_session(self, mock_session_local):
        """Test multiple database operations within a single session."""
        # Setup mock session
        mock_session = AsyncMock()
        mock_session_local.return_value = mock_session

        async with async_database_session() as session:
            await session.execute("INSERT INTO table1 VALUES (1)")
            await session.execute("UPDATE table2 SET col = 'value'")
            await session.execute("DELETE FROM table3 WHERE id = 1")

        # Verify all operations were called
        assert mock_session.execute.call_count == 3
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("areyouok_telegram.data.connection.AsyncSessionLocal")
    async def test_session_yields_correct_instance(self, mock_session_local):
        """Test that the context manager yields the correct session instance."""
        # Setup mock session
        mock_session = AsyncMock()
        mock_session_local.return_value = mock_session

        async with async_database_session() as session:
            # The yielded session should be the mock session
            assert session is mock_session

        mock_session_local.assert_called_once()


class TestDatabaseConfiguration:
    """Test database configuration setup."""

    def test_base_declarative_class_exists(self):
        """Test that the Base declarative class is properly configured."""

        # Base should be a declarative base class
        assert hasattr(Base, "metadata")
        assert hasattr(Base, "registry")

    def test_async_session_local_exists(self):
        """Test that AsyncSessionLocal is properly configured."""

        # AsyncSessionLocal should be a sessionmaker instance
        assert callable(AsyncSessionLocal)

        # Create a session instance to verify it's configured correctly
        session = AsyncSessionLocal()
        assert hasattr(session, "execute")
        assert hasattr(session, "commit")
        assert hasattr(session, "rollback")
        assert hasattr(session, "close")

    def test_async_engine_exists(self):
        """Test that the async engine is properly configured."""

        # Engine should have expected attributes
        assert hasattr(async_engine, "url")
        assert hasattr(async_engine, "dialect")

        # Verify it's using the postgresql+asyncpg driver
        assert str(async_engine.url).startswith("postgresql+asyncpg://")
