"""Tests for setup.database module."""

from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from areyouok_telegram.setup import database_setup


class TestDatabaseSetup:
    """Test cases for database_setup function."""

    @patch("areyouok_telegram.setup.database.create_engine")
    @patch("areyouok_telegram.setup.database.Base")
    def test_database_setup_success(self, mock_base, mock_create_engine):
        """Test successful database setup with schema and table creation."""
        # Arrange
        mock_engine = Mock()
        mock_conn = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_engine.begin.return_value.__enter__.return_value = mock_conn

        # Act
        database_setup()

        # Assert
        mock_create_engine.assert_called_once()
        mock_conn.execute.assert_called_once()  # Schema creation
        mock_base.metadata.create_all.assert_called_once_with(mock_conn)

    @patch("areyouok_telegram.setup.database.create_engine")
    def test_database_setup_connection_failure(self, mock_create_engine):
        """Test database setup handles connection failures gracefully."""
        # Arrange
        mock_create_engine.side_effect = SQLAlchemyError("Connection failed")

        # Act & Assert
        with pytest.raises(SQLAlchemyError, match="Connection failed"):
            database_setup()

    @patch("areyouok_telegram.setup.database.create_engine")
    @patch("areyouok_telegram.setup.database.Base")
    def test_database_setup_schema_creation_failure(self, mock_base, mock_create_engine):
        """Test database setup handles schema creation failures."""
        # Arrange
        mock_engine = Mock()
        mock_conn = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.side_effect = SQLAlchemyError("Schema creation failed")

        # Act & Assert
        with pytest.raises(SQLAlchemyError, match="Schema creation failed"):
            database_setup()

    @patch("areyouok_telegram.setup.database.create_engine")
    @patch("areyouok_telegram.setup.database.Base")
    def test_database_setup_table_creation_failure(self, mock_base, mock_create_engine):
        """Test database setup handles table creation failures."""
        # Arrange
        mock_engine = Mock()
        mock_conn = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_base.metadata.create_all.side_effect = SQLAlchemyError("Table creation failed")

        # Act & Assert
        with pytest.raises(SQLAlchemyError, match="Table creation failed"):
            database_setup()

    @patch("areyouok_telegram.setup.database.ENV", "test_environment")
    @patch("areyouok_telegram.setup.database.create_engine")
    @patch("areyouok_telegram.setup.database.CreateSchema")
    def test_database_setup_uses_correct_environment_schema(self, mock_create_schema, mock_create_engine):
        """Test database setup uses the correct environment for schema creation."""
        # Arrange
        mock_engine = Mock()
        mock_conn = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_engine.begin.return_value.__enter__.return_value = mock_conn

        # Act
        database_setup()

        # Assert
        mock_create_schema.assert_called_once_with("test_environment", if_not_exists=True)
