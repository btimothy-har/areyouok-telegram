"""Tests for chat utility functions."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from areyouok_telegram.data.models.context import ContextType
from areyouok_telegram.llms.utils import log_metadata_update_context


class TestLogMetadataUpdateContext:
    """Test log_metadata_update_context function."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.utils.async_database")
    @patch("areyouok_telegram.llms.utils.Chats.get_by_id")
    @patch("areyouok_telegram.llms.utils.Context.new_or_update")
    async def test_log_metadata_update_context_success(
        self, mock_context_update, mock_chats_get_by_id, mock_async_database
    ):
        """Test successful metadata update logging."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "test_encryption_key"
        mock_chats_get_by_id.return_value = mock_chat

        mock_context_update.return_value = None

        # Test data
        chat_id = "123456"
        session_id = "session_123"
        field = "communication_style"
        new_value = "casual and friendly"

        # Call function
        content = f"Updated usermeta: {field} is now {new_value}"
        await log_metadata_update_context(
            chat_id=chat_id,
            session_id=session_id,
            content=content,
        )

        # Verify database connection was created
        mock_async_database.assert_called_once()

        # Verify chat was retrieved with correct ID
        mock_chats_get_by_id.assert_called_once_with(mock_db_conn, chat_id=chat_id)

        # Verify encryption key was retrieved
        mock_chat.retrieve_key.assert_called_once()

        # Verify context was created with correct parameters
        mock_context_update.assert_called_once_with(
            mock_db_conn,
            chat_encryption_key="test_encryption_key",
            chat_id=chat_id,
            session_id=session_id,
            ctype=ContextType.METADATA.value,
            content=content,
        )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.utils.async_database")
    @patch("areyouok_telegram.llms.utils.Chats.get_by_id")
    async def test_log_metadata_update_context_chat_not_found(self, mock_chats_get_by_id, mock_async_database):
        """Test handling when chat object is not found."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock chat not found (returns None)
        mock_chats_get_by_id.return_value = None

        chat_id = "nonexistent_chat"
        session_id = "session_123"
        content = "Updated usermeta: preferred_name is now Alice"

        # Should raise AttributeError when trying to call retrieve_key on None
        with pytest.raises(AttributeError):
            await log_metadata_update_context(
                chat_id=chat_id,
                session_id=session_id,
                content=content,
            )

        # Verify chat lookup was attempted
        mock_chats_get_by_id.assert_called_once_with(mock_db_conn, chat_id=chat_id)

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.utils.async_database")
    @patch("areyouok_telegram.llms.utils.Chats.get_by_id")
    @patch("areyouok_telegram.llms.utils.Context.new_or_update")
    async def test_log_metadata_update_context_database_error(
        self, mock_context_update, mock_chats_get_by_id, mock_async_database
    ):
        """Test handling of database errors during context creation."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "test_encryption_key"
        mock_chats_get_by_id.return_value = mock_chat

        # Mock database error
        database_error = Exception("Database connection failed")
        mock_context_update.side_effect = database_error

        chat_id = "123456"
        session_id = "session_123"
        content = "Updated usermeta: timezone is now UTC"

        # Should propagate the database error
        with pytest.raises(Exception) as exc_info:
            await log_metadata_update_context(
                chat_id=chat_id,
                session_id=session_id,
                content=content,
            )

        assert exc_info.value == database_error

        # Verify all steps were attempted up to the error
        mock_chats_get_by_id.assert_called_once()
        mock_chat.retrieve_key.assert_called_once()
        mock_context_update.assert_called_once()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.utils.async_database")
    @patch("areyouok_telegram.llms.utils.Chats.get_by_id")
    @patch("areyouok_telegram.llms.utils.Context.new_or_update")
    async def test_log_metadata_update_context_different_content_formats(
        self, mock_context_update, mock_chats_get_by_id, mock_async_database
    ):
        """Test logging different content message formats."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "test_key"
        mock_chats_get_by_id.return_value = mock_chat

        # Test different content message formats
        test_cases = [
            "Updated usermeta: preferred_name is now John Doe",
            "Updated usermeta: country is now USA",
            "Updated usermeta: timezone is now America/New_York",
            "Updated usermeta: communication_style is now formal and professional",
        ]

        chat_id = "123456"
        session_id = "session_123"

        for expected_content in test_cases:
            # Reset mocks
            mock_context_update.reset_mock()

            await log_metadata_update_context(
                chat_id=chat_id,
                session_id=session_id,
                content=expected_content,
            )

            # Verify context was created with correct content
            mock_context_update.assert_called_once()
            call_args = mock_context_update.call_args
            assert call_args[1]["content"] == expected_content

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.utils.async_database")
    @patch("areyouok_telegram.llms.utils.Chats.get_by_id")
    @patch("areyouok_telegram.llms.utils.Context.new_or_update")
    async def test_log_metadata_update_context_parameter_validation(
        self, mock_context_update, mock_chats_get_by_id, mock_async_database
    ):
        """Test that all required parameters are passed correctly to Context.new_or_update."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_chat = MagicMock()
        encryption_key = "secure_encryption_key_12345"
        mock_chat.retrieve_key.return_value = encryption_key
        mock_chats_get_by_id.return_value = mock_chat

        # Test parameters
        chat_id = "chat_789"
        session_id = "session_456"
        content = "Updated usermeta: preferred_name is now Alice Smith"

        await log_metadata_update_context(
            chat_id=chat_id,
            session_id=session_id,
            content=content,
        )

        # Verify all parameters are correctly passed
        mock_context_update.assert_called_once()
        call_kwargs = mock_context_update.call_args[1]

        assert call_kwargs["chat_encryption_key"] == encryption_key
        assert call_kwargs["chat_id"] == chat_id
        assert call_kwargs["session_id"] == session_id
        assert call_kwargs["ctype"] == ContextType.METADATA.value
        assert call_kwargs["content"] == content

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.utils.async_database")
    @patch("areyouok_telegram.llms.utils.Chats.get_by_id")
    async def test_log_metadata_update_context_chat_retrieval_error(self, mock_chats_get_by_id, mock_async_database):
        """Test handling when chat retrieval fails."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock chat retrieval error
        chat_retrieval_error = Exception("Failed to retrieve chat")
        mock_chats_get_by_id.side_effect = chat_retrieval_error

        chat_id = "123456"
        session_id = "session_123"
        content = "Updated usermeta: communication_style is now updated style"

        # Should propagate the chat retrieval error
        with pytest.raises(Exception) as exc_info:
            await log_metadata_update_context(
                chat_id=chat_id,
                session_id=session_id,
                content=content,
            )

        assert exc_info.value == chat_retrieval_error
        mock_chats_get_by_id.assert_called_once_with(mock_db_conn, chat_id=chat_id)
