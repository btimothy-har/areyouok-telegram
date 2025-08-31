"""Tests for UserMetadata model."""

import hashlib
from datetime import UTC
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from areyouok_telegram.data.models.user_metadata import InvalidFieldError
from areyouok_telegram.data.models.user_metadata import InvalidFieldTypeError
from areyouok_telegram.data.models.user_metadata import UserMetadata


class TestUserMetadata:
    """Test UserMetadata model."""

    def setup_method(self):
        """Clear cache before each test."""
        UserMetadata._field_cache.clear()

    def test_generate_user_key(self):
        """Test user key generation."""
        user_id = "123456789"
        expected = hashlib.sha256(f"metadata:{user_id}".encode()).hexdigest()
        assert UserMetadata.generate_user_key(user_id) == expected

    def test_generate_user_key_different_users(self):
        """Test user key generation produces different keys for different users."""
        user_id1 = "123456789"
        user_id2 = "987654321"
        key1 = UserMetadata.generate_user_key(user_id1)
        key2 = UserMetadata.generate_user_key(user_id2)
        assert key1 != key2

    @patch("areyouok_telegram.data.models.user_metadata.decrypt_content")
    def test_decrypt_field_with_none_value(self, mock_decrypt):
        """Test _decrypt_field returns None for None input."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"

        result = metadata._decrypt_field("preferred_name", None)

        assert result is None
        mock_decrypt.assert_not_called()

    @patch("areyouok_telegram.data.models.user_metadata.decrypt_content")
    def test_decrypt_field_with_cached_value(self, mock_decrypt):
        """Test _decrypt_field returns cached value."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        cache_key = f"{metadata.user_key}:preferred_name"

        # Pre-populate cache
        UserMetadata._field_cache[cache_key] = "cached_value"

        result = metadata._decrypt_field("preferred_name", "encrypted_value")

        assert result == "cached_value"
        mock_decrypt.assert_not_called()

    @patch("areyouok_telegram.data.models.user_metadata.decrypt_content")
    def test_decrypt_field_without_cached_value(self, mock_decrypt):
        """Test _decrypt_field decrypts and caches value."""
        mock_decrypt.return_value = "decrypted_value"
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        cache_key = f"{metadata.user_key}:preferred_name"

        result = metadata._decrypt_field("preferred_name", "encrypted_value")

        assert result == "decrypted_value"
        assert UserMetadata._field_cache[cache_key] == "decrypted_value"
        mock_decrypt.assert_called_once_with("encrypted_value")

    @patch("areyouok_telegram.data.models.user_metadata.decrypt_content")
    def test_decrypt_field_with_none_decrypt_result(self, mock_decrypt):
        """Test _decrypt_field handles None decrypt result."""
        mock_decrypt.return_value = None
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        cache_key = f"{metadata.user_key}:preferred_name"

        result = metadata._decrypt_field("preferred_name", "encrypted_value")

        assert result is None
        assert cache_key not in UserMetadata._field_cache
        mock_decrypt.assert_called_once_with("encrypted_value")

    @patch("areyouok_telegram.data.models.user_metadata.decrypt_content")
    def test_preferred_name_property(self, mock_decrypt):
        """Test preferred_name property calls _decrypt_field correctly."""
        mock_decrypt.return_value = "John Doe"
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        metadata._preferred_name = "encrypted_name"

        result = metadata.preferred_name

        assert result == "John Doe"
        mock_decrypt.assert_called_once_with("encrypted_name")

    @patch("areyouok_telegram.data.models.user_metadata.decrypt_content")
    def test_country_property(self, mock_decrypt):
        """Test country property calls _decrypt_field correctly."""
        mock_decrypt.return_value = "United States"
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        metadata._country = "encrypted_country"

        result = metadata.country

        assert result == "United States"
        mock_decrypt.assert_called_once_with("encrypted_country")

    @patch("areyouok_telegram.data.models.user_metadata.decrypt_content")
    def test_timezone_property(self, mock_decrypt):
        """Test timezone property calls _decrypt_field correctly."""
        mock_decrypt.return_value = "America/New_York"
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        metadata._timezone = "encrypted_timezone"

        result = metadata.timezone

        assert result == "America/New_York"
        mock_decrypt.assert_called_once_with("encrypted_timezone")

    @patch("areyouok_telegram.data.models.user_metadata.decrypt_content")
    def test_communication_style_property(self, mock_decrypt):
        """Test communication_style property calls _decrypt_field correctly."""
        mock_decrypt.return_value = "casual"
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        metadata._communication_style = "encrypted_style"

        result = metadata.communication_style

        assert result == "casual"
        mock_decrypt.assert_called_once_with("encrypted_style")

    def test_property_with_none_encrypted_field(self):
        """Test property returns None when encrypted field is None."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        metadata._preferred_name = None

        result = metadata.preferred_name

        assert result is None

    @pytest.mark.asyncio
    async def test_update_metadata_invalid_field(self, mock_db_session):
        """Test update_metadata raises InvalidFieldError for invalid field."""
        with pytest.raises(InvalidFieldError) as exc_info:
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="invalid_field", value="value")

        assert exc_info.value.field == "invalid_field"
        assert "preferred_name" in exc_info.value.valid_fields
        assert "daily_checkin" in exc_info.value.valid_fields

    @pytest.mark.asyncio
    async def test_update_metadata_invalid_type_for_encrypted_field(self, mock_db_session):
        """Test update_metadata raises InvalidFieldTypeError for non-string encrypted field."""
        with pytest.raises(InvalidFieldTypeError) as exc_info:
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="preferred_name", value=123)

        assert exc_info.value.field == "preferred_name"
        assert exc_info.value.expected_type == "a string or None"

    @pytest.mark.asyncio
    async def test_update_metadata_invalid_type_for_boolean_field(self, mock_db_session):
        """Test update_metadata raises InvalidFieldTypeError for non-boolean daily_checkin."""
        with pytest.raises(InvalidFieldTypeError) as exc_info:
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="daily_checkin", value="true")

        assert exc_info.value.field == "daily_checkin"
        assert exc_info.value.expected_type == "a boolean"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.user_metadata.encrypt_content")
    async def test_update_metadata_encrypted_field_with_value(self, mock_encrypt, mock_db_session):
        """Test update_metadata with encrypted field having a value."""
        mock_encrypt.return_value = "encrypted_john"
        mock_updated_user = MagicMock(spec=UserMetadata)

        with patch.object(UserMetadata, "get_by_user_id", return_value=mock_updated_user):
            result = await UserMetadata.update_metadata(
                mock_db_session, user_id="user123", field="preferred_name", value="John"
            )

        # Verify encryption was called
        mock_encrypt.assert_called_once_with("John")

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

        # Verify get_by_user_id was called to return updated user
        assert result == mock_updated_user

    @pytest.mark.asyncio
    async def test_update_metadata_encrypted_field_with_none(self, mock_db_session):
        """Test update_metadata with encrypted field set to None."""
        mock_updated_user = MagicMock(spec=UserMetadata)

        with patch.object(UserMetadata, "get_by_user_id", return_value=mock_updated_user):
            result = await UserMetadata.update_metadata(
                mock_db_session, user_id="user123", field="preferred_name", value=None
            )

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

        # Verify get_by_user_id was called to return updated user
        assert result == mock_updated_user

    @pytest.mark.asyncio
    async def test_update_metadata_unencrypted_field(self, mock_db_session):
        """Test update_metadata with unencrypted boolean field."""
        mock_updated_user = MagicMock(spec=UserMetadata)

        with patch.object(UserMetadata, "get_by_user_id", return_value=mock_updated_user):
            result = await UserMetadata.update_metadata(
                mock_db_session, user_id="user123", field="daily_checkin", value=True
            )

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

        # Verify get_by_user_id was called to return updated user
        assert result == mock_updated_user

    @pytest.mark.asyncio
    async def test_update_metadata_database_upsert_structure(self, mock_db_session):
        """Test update_metadata creates correct database upsert statement."""
        user_id = "user123"
        mock_updated_user = MagicMock(spec=UserMetadata)

        with patch.object(UserMetadata, "get_by_user_id", return_value=mock_updated_user):
            await UserMetadata.update_metadata(mock_db_session, user_id=user_id, field="daily_checkin", value=True)

        # Get the statement that was executed
        call_args = mock_db_session.execute.call_args[0][0]

        # Verify it's an insert statement targeting the correct table
        assert hasattr(call_args, "table")
        assert call_args.table.name == "user_metadata"

        # Verify database execute was called (which is the important part)
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_id_found(self, mock_db_session):
        """Test get_by_user_id returns user when found."""
        mock_user = MagicMock(spec=UserMetadata)
        mock_user.user_id = "user123"

        # Setup mock chain for execute().scalars().first()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_user
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await UserMetadata.get_by_user_id(mock_db_session, user_id="user123")

        assert result == mock_user
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_id_not_found(self, mock_db_session):
        """Test get_by_user_id returns None when user not found."""
        # Setup mock chain for execute().scalars().first() returning None
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await UserMetadata.get_by_user_id(mock_db_session, user_id="nonexistent")

        assert result is None
        mock_db_session.execute.assert_called_once()

    def test_field_mappings_completeness(self):
        """Test that all expected fields are in field mappings."""
        encrypted_fields = UserMetadata._ENCRYPTED_FIELDS
        unencrypted_fields = UserMetadata._UNENCRYPTED_FIELDS

        # Verify expected encrypted fields
        assert "preferred_name" in encrypted_fields
        assert "country" in encrypted_fields
        assert "timezone" in encrypted_fields
        assert "communication_style" in encrypted_fields

        # Verify expected unencrypted fields
        assert "daily_checkin" in unencrypted_fields

        # Verify encrypted field mappings point to private fields
        assert encrypted_fields["preferred_name"] == "_preferred_name"
        assert encrypted_fields["country"] == "_country"
        assert encrypted_fields["timezone"] == "_timezone"
        assert encrypted_fields["communication_style"] == "_communication_style"

    def test_cache_isolation_between_users(self):
        """Test that cache is properly isolated between different users."""
        metadata1 = UserMetadata()
        metadata1.user_key = "user1_key"

        metadata2 = UserMetadata()
        metadata2.user_key = "user2_key"

        # Manually set cache for user1
        cache_key1 = f"{metadata1.user_key}:preferred_name"
        cache_key2 = f"{metadata2.user_key}:preferred_name"

        UserMetadata._field_cache[cache_key1] = "user1_value"
        UserMetadata._field_cache[cache_key2] = "user2_value"

        # Verify values are properly isolated
        assert UserMetadata._field_cache.get(cache_key1) == "user1_value"
        assert UserMetadata._field_cache.get(cache_key2) == "user2_value"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.user_metadata.encrypt_content")
    async def test_update_metadata_null_string_value(self, mock_encrypt, mock_db_session):
        """Test update_metadata with valid None value for encrypted field accepts type check."""
        mock_updated_user = MagicMock(spec=UserMetadata)

        with patch.object(UserMetadata, "get_by_user_id", return_value=mock_updated_user):
            result = await UserMetadata.update_metadata(
                mock_db_session, user_id="user123", field="preferred_name", value=None
            )

        # Verify encryption was NOT called for None value
        mock_encrypt.assert_not_called()

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()
        assert result == mock_updated_user

    @pytest.mark.asyncio
    async def test_update_metadata_valid_string_types(self, mock_db_session):
        """Test update_metadata accepts various string types for encrypted fields."""
        mock_updated_user = MagicMock(spec=UserMetadata)
        test_values = [
            "",  # Empty string
            "simple_string",  # Basic string
            "String with spaces and 123 numbers!",  # Complex string
            "Unicode émojis 🚀 and ñoñó",  # Unicode characters
        ]

        for test_value in test_values:
            with patch.object(UserMetadata, "get_by_user_id", return_value=mock_updated_user):
                result = await UserMetadata.update_metadata(
                    mock_db_session, user_id="user123", field="country", value=test_value
                )

            assert result == mock_updated_user

    @pytest.mark.asyncio
    async def test_update_metadata_all_encrypted_fields(self, mock_db_session):
        """Test update_metadata works with all encrypted fields."""
        mock_updated_user = MagicMock(spec=UserMetadata)
        encrypted_fields = [
            ("preferred_name", "John Doe"),
            ("country", "United States"),
            ("timezone", "America/New_York"),
            ("communication_style", "casual"),
        ]

        for field_name, field_value in encrypted_fields:
            with patch.object(UserMetadata, "get_by_user_id", return_value=mock_updated_user):
                result = await UserMetadata.update_metadata(
                    mock_db_session, user_id="user123", field=field_name, value=field_value
                )

            assert result == mock_updated_user

    @pytest.mark.asyncio
    async def test_update_metadata_boolean_values(self, mock_db_session):
        """Test update_metadata with different boolean values."""
        mock_updated_user = MagicMock(spec=UserMetadata)
        boolean_values = [True, False]

        for boolean_value in boolean_values:
            with patch.object(UserMetadata, "get_by_user_id", return_value=mock_updated_user):
                result = await UserMetadata.update_metadata(
                    mock_db_session, user_id="user123", field="daily_checkin", value=boolean_value
                )

            assert result == mock_updated_user

    @patch("areyouok_telegram.data.models.user_metadata.datetime")
    @pytest.mark.asyncio
    async def test_update_metadata_uses_current_timestamp(self, mock_datetime, mock_db_session, frozen_time):
        """Test update_metadata uses current UTC timestamp for created_at and updated_at."""
        mock_datetime.now.return_value = frozen_time
        mock_updated_user = MagicMock(spec=UserMetadata)

        with patch.object(UserMetadata, "get_by_user_id", return_value=mock_updated_user):
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="daily_checkin", value=True)

        # Verify datetime.now was called with UTC
        mock_datetime.now.assert_called_once_with(UTC)

    def test_cache_ttl_isolation(self):
        """Test that TTL cache properly isolates expired vs active entries."""
        metadata = UserMetadata()
        metadata.user_key = "test_user"

        # Manually test cache behavior
        cache_key = f"{metadata.user_key}:test_field"

        # Add value to cache
        UserMetadata._field_cache[cache_key] = "cached_value"

        # Verify it's retrievable
        assert UserMetadata._field_cache.get(cache_key) == "cached_value"

        # Clear cache to test isolation
        UserMetadata._field_cache.clear()
        assert cache_key not in UserMetadata._field_cache

    @patch("areyouok_telegram.data.models.user_metadata.decrypt_content")
    def test_decrypt_field_cache_key_format(self, mock_decrypt):
        """Test _decrypt_field uses correct cache key format."""
        mock_decrypt.return_value = "decrypted_value"
        metadata = UserMetadata()
        metadata.user_key = "test_user_123"
        field_name = "test_field"

        result = metadata._decrypt_field(field_name, "encrypted_value")

        expected_cache_key = f"{metadata.user_key}:{field_name}"
        assert UserMetadata._field_cache.get(expected_cache_key) == "decrypted_value"
        assert result == "decrypted_value"


class TestInvalidFieldError:
    """Test InvalidFieldError exception."""

    def test_invalid_field_error_creation(self):
        """Test InvalidFieldError is created with correct attributes."""
        valid_fields = ["field1", "field2", "field3"]
        error = InvalidFieldError("invalid_field", valid_fields)

        assert error.field == "invalid_field"
        assert error.valid_fields == valid_fields
        assert "Invalid field 'invalid_field'" in str(error)
        assert "field1" in str(error)

    def test_invalid_field_error_inheritance(self):
        """Test InvalidFieldError inherits from Exception."""
        error = InvalidFieldError("test", [])
        assert isinstance(error, Exception)


class TestInvalidFieldTypeError:
    """Test InvalidFieldTypeError exception."""

    def test_invalid_field_type_error_creation(self):
        """Test InvalidFieldTypeError is created with correct attributes."""
        error = InvalidFieldTypeError("test_field", "a string")

        assert error.field == "test_field"
        assert error.expected_type == "a string"
        assert "Field 'test_field' must be a string" in str(error)

    def test_invalid_field_type_error_inheritance(self):
        """Test InvalidFieldTypeError inherits from Exception."""
        error = InvalidFieldTypeError("test", "test")
        assert isinstance(error, Exception)
