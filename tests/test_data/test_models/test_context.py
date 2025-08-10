"""Tests for Context model."""

import hashlib
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from areyouok_telegram.data.models.context import Context
from areyouok_telegram.data.models.context import InvalidContextTypeError


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
    async def test_new_or_update_valid_type(self, mock_db_session):
        """Test inserting a new context with valid type."""
        mock_result = AsyncMock()
        mock_db_session.execute.return_value = mock_result
        user_key = Fernet.generate_key().decode("utf-8")

        await Context.new_or_update(
            mock_db_session, user_key, chat_id="123", session_id="session_456", ctype="session", content="test content"
        )

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify the statement is for context table
        call_args = mock_db_session.execute.call_args[0][0]
        assert hasattr(call_args, "table")
        assert call_args.table.name == "context"

    @pytest.mark.asyncio
    async def test_new_or_update_invalid_type(self, mock_db_session):
        """Test inserting a context with invalid type raises error."""
        user_key = Fernet.generate_key().decode("utf-8")

        with pytest.raises(InvalidContextTypeError) as exc_info:
            await Context.new_or_update(
                mock_db_session,
                user_key,
                chat_id="123",
                session_id="session_456",
                ctype="invalid_type",
                content="test content",
            )

        assert exc_info.value.context_type == "invalid_type"
        mock_db_session.execute.assert_not_called()

    def test_encrypt_content(self):
        """Test content encryption."""
        content = "test content to encrypt"
        user_key = Fernet.generate_key().decode("utf-8")

        encrypted = Context.encrypt_content(content, user_key)

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
        encrypted = Context.encrypt_content(content, user_key)

        # Create context instance with encrypted content
        ctx = Context()
        ctx.encrypted_content = encrypted

        # Decrypt should return original content
        decrypted = ctx.decrypt_content(user_key)
        assert decrypted == content

    def test_decrypt_content_no_encrypted_content(self):
        """Test decrypt_content returns None when no encrypted content."""
        ctx = Context()
        ctx.encrypted_content = None
        user_key = Fernet.generate_key().decode("utf-8")

        result = ctx.decrypt_content(user_key)
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

        result = await Context.get_by_session_id(mock_db_session, "session_456")

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

        result = await Context.get_by_session_id(mock_db_session, "nonexistent")

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

        result = await Context.get_by_session_id(mock_db_session, "session_456", ctype="session")

        assert result == [mock_context]
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_session_id_invalid_type(self, mock_db_session):
        """Test retrieving contexts with invalid type raises error."""
        with pytest.raises(InvalidContextTypeError):
            await Context.get_by_session_id(mock_db_session, "session_456", ctype="invalid")

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

        result = await Context.get_by_chat_id(mock_db_session, "123")

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

        result = await Context.retrieve_context_by_chat(mock_db_session, "123", limit=2)

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

        result = await Context.retrieve_context_by_chat(mock_db_session, "123")

        assert result is None
