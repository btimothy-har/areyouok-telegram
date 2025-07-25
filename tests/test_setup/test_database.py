"""Tests for setup.database module."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from areyouok_telegram.setup import database_setup


@pytest.fixture(autouse=True)
def mock_base():
    """Fixture for mocking SQLAlchemy Base."""
    with patch("areyouok_telegram.data.Base") as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_engine_creation():
    """Fixture for mocking SQLAlchemy create_engine."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn

    with patch("areyouok_telegram.setup.database.create_engine") as mock_create_engine:
        mock_create_engine.return_value = mock_engine
        yield mock_create_engine, mock_conn, mock_engine


class TestDatabaseSetup:
    """Test cases for database_setup function."""

    def test_database_setup_success(self, mock_engine_creation, mock_base):
        """Test successful database setup with schema and table creation."""
        mock_create_engine, mock_conn, _ = mock_engine_creation

        database_setup()

        # Assert
        mock_create_engine.assert_called_once()
        mock_conn.execute.assert_called_once()  # Schema creation
        mock_base.metadata.create_all.assert_called_once_with(mock_conn)

    def test_database_setup_connection_failure(self, mock_engine_creation):
        """Test database setup handles connection failures gracefully."""
        # Arrange
        mock_create_engine, _, _ = mock_engine_creation
        mock_create_engine.side_effect = SQLAlchemyError("Connection failed")

        # Act & Assert
        with pytest.raises(SQLAlchemyError, match="Connection failed"):
            database_setup()

    def test_database_setup_schema_creation_failure(self, mock_engine_creation):  # noqa: ARG002
        """Test database setup handles schema creation failures."""
        # Arrange
        _, mock_conn, _ = mock_engine_creation
        mock_conn.execute.side_effect = SQLAlchemyError("Schema creation failed")

        # Act & Assert
        with pytest.raises(SQLAlchemyError, match="Schema creation failed"):
            database_setup()

    def test_database_setup_table_creation_failure(self, mock_base):
        """Test database setup handles table creation failures."""
        # Arrange
        mock_base.metadata.create_all.side_effect = SQLAlchemyError("Table creation failed")

        # Act & Assert
        with pytest.raises(SQLAlchemyError, match="Table creation failed"):
            database_setup()

    @patch("areyouok_telegram.setup.database.ENV", "test_environment")
    def test_database_setup_uses_correct_environment_schema(self):
        """Test database setup uses the correct environment for schema creation."""
        with patch("areyouok_telegram.setup.database.CreateSchema") as mock_create_schema:
            # Arrange
            mock_create_schema.return_value = MagicMock()

            # Act
            database_setup()

            # Assert
            mock_create_schema.assert_called_once_with("test_environment", if_not_exists=True)
