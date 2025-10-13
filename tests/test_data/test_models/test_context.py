"""Tests for Context model."""

import hashlib
import json
from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from areyouok_telegram.data.models.context import Context
from areyouok_telegram.data.models.context import InvalidContextTypeError
from areyouok_telegram.encryption.exceptions import ContentNotDecryptedError


class TestContext:
    """Test Context model."""

    def test_generate_context_key(self):
        """Test context key generation."""
        chat_id = "123"
        ctype = "session"
        encrypted_content = "encrypted_test_content"

        expected = hashlib.sha256(f"{chat_id}:{ctype}:{encrypted_content}".encode()).hexdigest()
        assert Context.generate_context_key(chat_id, ctype, encrypted_content) == expected

    @pytest.mark.asyncio
    async def test_new_valid_type(self, mock_db_session):
        """Test inserting a new context with valid type."""
        mock_result = MagicMock()
        mock_db_session.execute.return_value = mock_result
        user_key = Fernet.generate_key().decode("utf-8")

        await Context.new(
            mock_db_session,
            chat_encryption_key=user_key,
            chat_id="123",
            session_id="session_456",
            ctype="session",
            content="test content",
        )

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify the statement is for context table
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "table")
        assert call_args.table.name == "context"

    @pytest.mark.asyncio
    async def test_new_invalid_type(self, mock_db_session):
        """Test inserting a context with invalid type raises error."""
        user_key = Fernet.generate_key().decode("utf-8")

        with pytest.raises(InvalidContextTypeError) as exc_info:
            await Context.new(
                mock_db_session,
                chat_encryption_key=user_key,
                chat_id="123",
                session_id="session_456",
                ctype="invalid_type",
                content="test content",
            )

        assert exc_info.value.context_type == "invalid_type"
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_memory_type(self, mock_db_session):
        """Test inserting a context with MEMORY type."""
        mock_result = MagicMock()
        mock_db_session.execute.return_value = mock_result
        user_key = Fernet.generate_key().decode("utf-8")

        await Context.new(
            mock_db_session,
            chat_encryption_key=user_key,
            chat_id="123",
            session_id="session_456",
            ctype="memory",
            content="User prefers morning check-ins",
        )

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify the statement is for context table
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "table")
        assert call_args.table.name == "context"

    def test_encrypt_content(self):
        """Test content encryption."""
        content = "test content to encrypt"
        user_key = Fernet.generate_key().decode("utf-8")

        encrypted = Context.encrypt_content(content=content, chat_encryption_key=user_key)

        # Should be a string (base64 encoded encrypted data)
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0

        # Should be able to decrypt it back
        fernet = Fernet(user_key.encode())
        decrypted_bytes = fernet.decrypt(encrypted.encode("utf-8"))
        decrypted_content = decrypted_bytes.decode("utf-8")
        assert decrypted_content == content

    def test_decrypt_content(self):
        """Test content decryption."""
        content = "another test content"
        user_key = Fernet.generate_key().decode("utf-8")

        # First encrypt
        encrypted = Context.encrypt_content(content=content, chat_encryption_key=user_key)

        # Create context instance with encrypted content
        ctx = Context()
        ctx.encrypted_content = encrypted

        # Decrypt should return original content
        decrypted = ctx.decrypt_content(chat_encryption_key=user_key)
        assert decrypted == content

    def test_decrypt_content_no_encrypted_content(self):
        """Test decrypt_content returns None when no encrypted content."""
        ctx = Context()
        ctx.encrypted_content = None
        user_key = Fernet.generate_key().decode("utf-8")

        result = ctx.decrypt_content(chat_encryption_key=user_key)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_session_id_found(self, mock_db_session):
        """Test retrieving contexts by session ID."""
        # Create mock context results
        mock_context1 = MagicMock(spec=Context)
        mock_context2 = MagicMock(spec=Context)

        # Setup mock chain for execute().scalars().all()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_context1, mock_context2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Context.get_by_session_id(mock_db_session, session_id="session_456")

        assert result == [mock_context1, mock_context2]
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_session_id_not_found(self, mock_db_session):
        """Test retrieving contexts by session ID when not found."""
        # Setup mock chain for execute().scalars().all() returning empty list
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Context.get_by_session_id(mock_db_session, session_id="nonexistent")

        assert result is None
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_session_id_with_type_filter(self, mock_db_session):
        """Test retrieving contexts by session ID with type filter."""
        mock_context = MagicMock(spec=Context)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_context]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Context.get_by_session_id(mock_db_session, session_id="session_456", ctype="session")

        assert result == [mock_context]
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_session_id_invalid_type(self, mock_db_session):
        """Test retrieving contexts with invalid type raises error."""
        with pytest.raises(InvalidContextTypeError):
            await Context.get_by_session_id(mock_db_session, session_id="session_456", ctype="invalid")

        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_by_chat_id_found(self, mock_db_session):
        """Test retrieving contexts by chat ID."""
        mock_context = MagicMock(spec=Context)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_context]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Context.get_by_chat_id(mock_db_session, chat_id="123")

        assert result == [mock_context]
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_context_by_chat_with_limit(self, mock_db_session):
        """Test retrieving contexts by chat with limit."""
        mock_context1 = MagicMock(spec=Context)
        mock_context2 = MagicMock(spec=Context)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_context1, mock_context2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Context.retrieve_context_by_chat(mock_db_session, chat_id="123")

        assert result == [mock_context1, mock_context2]
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_context_by_chat_empty(self, mock_db_session):
        """Test retrieving contexts returns None when empty."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Context.retrieve_context_by_chat(mock_db_session, chat_id="123")

        assert result is None

    def test_content_property_cache_miss(self):
        """Test content property raises error when not in cache (lines 98-102)."""
        ctx = Context()
        ctx.context_key = "test_key_not_in_cache"

        # Clear cache to ensure cache miss
        Context._data_cache.clear()

        with pytest.raises(ContentNotDecryptedError) as exc_info:
            _ = ctx.content

        # Check that the exception contains the correct field name
        expected_message = (
            "Content for field 'test_key_not_in_cache' has not been decrypted yet. Call decrypt_content() first."
        )
        assert str(exc_info.value) == expected_message
        assert exc_info.value.field_name == "test_key_not_in_cache"

    def test_content_property_cache_hit(self):
        """Test content property returns decrypted data from cache."""
        ctx = Context()
        ctx.context_key = "test_key_in_cache"

        # Populate cache with test data
        test_data = {"message": "test content"}
        test_bytes = json.dumps(test_data).encode("utf-8")
        Context._data_cache[ctx.context_key] = test_bytes

        result = ctx.content
        assert result == test_data

    @pytest.mark.asyncio
    async def test_get_by_chat_id_invalid_type(self, mock_db_session):
        """Test get_by_chat_id with invalid type raises error (line 184)."""
        with pytest.raises(InvalidContextTypeError) as exc_info:
            await Context.get_by_chat_id(mock_db_session, chat_id="123", ctype="invalid_type")

        assert exc_info.value.context_type == "invalid_type"
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_by_chat_id_with_type_filter(self, mock_db_session):
        """Test get_by_chat_id with type filter applies WHERE clause (line 189)."""
        mock_context = MagicMock(spec=Context)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_context]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Context.get_by_chat_id(mock_db_session, chat_id="123", ctype="session")

        assert result == [mock_context]
        mock_db_session.execute.assert_called_once()

        # Verify the SQL query includes the type filter
        call_args = mock_db_session.execute.call_args[0][0]
        # The statement should be a select with where clauses for both chat_id and type
        assert hasattr(call_args, "whereclause")

    @pytest.mark.asyncio
    async def test_retrieve_context_by_chat_invalid_type(self, mock_db_session):
        """Test retrieve_context_by_chat with invalid type raises error (line 208)."""
        with pytest.raises(InvalidContextTypeError) as exc_info:
            await Context.retrieve_context_by_chat(mock_db_session, chat_id="123", ctype="invalid_type")

        assert exc_info.value.context_type == "invalid_type"
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_retrieve_context_by_chat_with_type_filter(self, mock_db_session):
        """Test retrieve_context_by_chat with type filter applies WHERE clause (line 213)."""
        mock_context1 = MagicMock(spec=Context)
        mock_context2 = MagicMock(spec=Context)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_context1, mock_context2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Context.retrieve_context_by_chat(mock_db_session, chat_id="123", ctype="response")

        assert result == [mock_context1, mock_context2]
        mock_db_session.execute.assert_called_once()

        # Verify the SQL query includes the type filter
        call_args = mock_db_session.execute.call_args[0][0]
        # The statement should be a select with where clauses for both chat_id and type
        assert hasattr(call_args, "whereclause")

    @pytest.mark.asyncio
    async def test_get_by_ids_empty_list(self, mock_db_session):
        """Test get_by_ids with empty list returns empty list (line 247-248)."""
        result = await Context.get_by_ids(mock_db_session, ids=[])

        assert result == []
        # Execute should NOT be called for empty list
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_by_ids_with_ids(self, mock_db_session):
        """Test get_by_ids retrieves contexts by IDs (lines 250-252)."""
        mock_context1 = MagicMock(spec=Context)
        mock_context1.id = 1
        mock_context2 = MagicMock(spec=Context)
        mock_context2.id = 2

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_context1, mock_context2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await Context.get_by_ids(mock_db_session, ids=[1, 2])

        assert result == [mock_context1, mock_context2]
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_created_timestamp(self, mock_db_session):
        """Test get_by_created_timestamp retrieves contexts in time range (lines 273-280)."""
        mock_context1 = MagicMock(spec=Context)
        mock_context2 = MagicMock(spec=Context)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_context1, mock_context2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        from_time = datetime(2025, 1, 1, tzinfo=UTC)
        to_time = datetime(2025, 1, 31, tzinfo=UTC)

        result = await Context.get_by_created_timestamp(mock_db_session, from_timestamp=from_time, to_timestamp=to_time)

        assert result == [mock_context1, mock_context2]
        mock_db_session.execute.assert_called_once()
