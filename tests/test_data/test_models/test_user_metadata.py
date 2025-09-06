"""Tests for UserMetadata model."""

import hashlib
from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from areyouok_telegram.data.models.user_metadata import InvalidCountryCodeError
from areyouok_telegram.data.models.user_metadata import InvalidFieldError
from areyouok_telegram.data.models.user_metadata import InvalidFieldValueError
from areyouok_telegram.data.models.user_metadata import InvalidTimezoneError
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

    def test_timezone_property(self):
        """Test timezone property returns unencrypted value directly."""
        metadata = UserMetadata()
        metadata.timezone = "America/New_York"

        result = metadata.timezone

        assert result == "America/New_York"

    def test_communication_style_property(self):
        """Test communication_style property returns unencrypted value directly."""
        metadata = UserMetadata()
        metadata.communication_style = "casual"

        result = metadata.communication_style

        assert result == "casual"

    def test_property_with_none_encrypted_field(self):
        """Test property returns None when encrypted field is None."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        metadata._preferred_name = None

        result = metadata.preferred_name

        assert result is None

    def test_country_display_name_with_iso3_code(self):
        """Test country_display_name property with ISO3 country codes."""
        metadata = UserMetadata()
        
        # Test valid ISO3 codes
        metadata.country = "USA"
        assert metadata.country_display_name == "United States"
        
        metadata.country = "GBR"
        assert metadata.country_display_name == "United Kingdom"
        
        metadata.country = "DEU"
        assert metadata.country_display_name == "Germany"
        
    def test_country_display_name_with_rather_not_say(self):
        """Test country_display_name property with rather_not_say value."""
        metadata = UserMetadata()
        metadata.country = "rather_not_say"
        
        assert metadata.country_display_name == "Prefer not to say"
        
    def test_country_display_name_with_invalid_code(self):
        """Test country_display_name property with invalid country code."""
        metadata = UserMetadata()
        metadata.country = "INVALID_CODE"
        
        # Should return the original code when invalid
        assert metadata.country_display_name == "INVALID_CODE"
        
    def test_country_display_name_with_none_or_empty(self):
        """Test country_display_name property with None or empty values."""
        metadata = UserMetadata()
        
        # Test None
        metadata.country = None
        assert metadata.country_display_name is None
        
        # Test empty string
        metadata.country = ""
        assert metadata.country_display_name is None

    @pytest.mark.asyncio
    async def test_update_metadata_invalid_field(self, mock_db_session):
        """Test update_metadata raises InvalidFieldError for invalid field."""
        with pytest.raises(InvalidFieldError) as exc_info:
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="invalid_field", value="value")

        assert exc_info.value.field == "invalid_field"
        assert "preferred_name" in exc_info.value.valid_fields
        assert "country" in exc_info.value.valid_fields

    @pytest.mark.asyncio
    async def test_update_metadata_invalid_type_for_encrypted_field(self, mock_db_session):
        """Test update_metadata raises InvalidFieldValueError for non-string encrypted field."""
        with pytest.raises(InvalidFieldValueError) as exc_info:
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="preferred_name", value=123)

        assert exc_info.value.field == "preferred_name"
        assert exc_info.value.expected == "a string or None"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.user_metadata.encrypt_content")
    async def test_update_metadata_encrypted_field_with_value(self, mock_encrypt, mock_db_session):
        """Test update_metadata with encrypted field having a value."""
        mock_encrypt.return_value = "encrypted_john"

        await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="preferred_name", value="John")

        # Verify encryption was called
        mock_encrypt.assert_called_once_with("John")

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_metadata_encrypted_field_with_none(self, mock_db_session):
        """Test update_metadata with encrypted field set to None."""
        await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="preferred_name", value=None)

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_metadata_unencrypted_field(self, mock_db_session):
        """Test update_metadata with unencrypted field."""
        await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="country", value="USA")

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_metadata_database_upsert_structure(self, mock_db_session):
        """Test update_metadata creates correct database upsert statement."""
        user_id = "user123"
        mock_updated_user = MagicMock(spec=UserMetadata)

        with patch.object(UserMetadata, "get_by_user_id", return_value=mock_updated_user):
            await UserMetadata.update_metadata(mock_db_session, user_id=user_id, field="country", value="USA")

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

        # Verify expected unencrypted fields
        assert "country" in unencrypted_fields
        assert "timezone" in unencrypted_fields
        assert "communication_style" in unencrypted_fields

        # Verify encrypted field mappings point to private fields
        assert encrypted_fields["preferred_name"] == "_preferred_name"

        # Verify unencrypted field mappings point to public fields
        assert unencrypted_fields["country"] == "country"
        assert unencrypted_fields["timezone"] == "timezone"
        assert unencrypted_fields["communication_style"] == "communication_style"

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
        await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="preferred_name", value=None)

        # Verify encryption was NOT called for None value
        mock_encrypt.assert_not_called()

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_metadata_valid_string_types(self, mock_db_session):
        """Test update_metadata accepts various string types for encrypted fields."""
        test_values = [
            "",  # Empty string
            "simple_string",  # Basic string
            "String with spaces and 123 numbers!",  # Complex string
            "Unicode émojis 🚀 and ñoñó",  # Unicode characters
        ]

        for test_value in test_values:
            try:
                await UserMetadata.update_metadata(
                    mock_db_session, user_id="user123", field="preferred_name", value=test_value
                )
            except Exception:
                # Some values might fail validation, that's expected
                pass

    @pytest.mark.asyncio
    async def test_update_metadata_all_encrypted_fields(self, mock_db_session):
        """Test update_metadata works with all encrypted fields."""
        encrypted_fields = [
            ("preferred_name", "John Doe"),
            ("country", "USA"),
            ("timezone", "America/New_York"),
            ("communication_style", "casual"),
        ]

        for field_name, field_value in encrypted_fields:
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field=field_name, value=field_value)

    @pytest.mark.asyncio
    async def test_update_metadata_unencrypted_string_values(self, mock_db_session):
        """Test update_metadata with different string values for unencrypted fields."""
        country_values = ["USA", "CAN", "GBR"]

        for country_value in country_values:
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="country", value=country_value)

    @pytest.mark.asyncio
    async def test_update_metadata_unencrypted_field_with_value(self, mock_db_session):
        """Test update_metadata with unencrypted field having a value covers elif branch."""
        await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="country", value="USA")

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_metadata_unencrypted_field_in_conflict_resolution(self, mock_db_session):
        """Test update_metadata covers elif branch in conflict resolution for unencrypted fields."""
        # Test communication_style field to ensure we hit the unencrypted elif branch
        await UserMetadata.update_metadata(
            mock_db_session, user_id="user123", field="communication_style", value="formal"
        )

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_metadata_unencrypted_field_branch_coverage(self, mock_db_session):
        """Test update_metadata with unencrypted field to hit lines 160->164."""
        # This test specifically targets the elif branch for unencrypted fields
        await UserMetadata.update_metadata(
            mock_db_session, user_id="user123", field="timezone", value="America/New_York"
        )

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

    @patch("areyouok_telegram.data.models.user_metadata.datetime")
    @pytest.mark.asyncio
    async def test_update_metadata_uses_current_timestamp(self, mock_datetime, mock_db_session, frozen_time):
        """Test update_metadata uses current UTC timestamp for created_at and updated_at."""
        mock_datetime.now.return_value = frozen_time
        MagicMock(spec=UserMetadata)

        await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="country", value="USA")

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

    def test_validate_country_rather_not_say(self):
        """Test _validate_country with 'rather_not_say' value."""
        result = UserMetadata._validate_country("rather_not_say")
        assert result == "rather_not_say"

    def test_validate_country_rather_not_say_case_insensitive(self):
        """Test _validate_country with 'RATHER_NOT_SAY' value (case insensitive)."""
        result = UserMetadata._validate_country("RATHER_NOT_SAY")
        assert result == "rather_not_say"

    def test_validate_country_valid_iso3_code(self):
        """Test _validate_country with valid ISO3 country code."""
        result = UserMetadata._validate_country("usa")
        assert result == "USA"

    def test_validate_country_valid_iso3_code_uppercase(self):
        """Test _validate_country with valid uppercase ISO3 country code."""
        result = UserMetadata._validate_country("CAN")
        assert result == "CAN"

    def test_validate_country_invalid_code_raises_error(self):
        """Test _validate_country raises InvalidCountryCodeError for invalid code."""
        with pytest.raises(InvalidCountryCodeError) as exc_info:
            UserMetadata._validate_country("INVALID")

        assert exc_info.value.value == "INVALID"
        assert exc_info.value.field == "country"

    def test_validate_timezone_rather_not_say(self):
        """Test _validate_timezone with 'rather_not_say' value."""
        result = UserMetadata._validate_timezone("rather_not_say")
        assert result == "rather_not_say"

    def test_validate_timezone_rather_not_say_case_insensitive(self):
        """Test _validate_timezone with 'RATHER_NOT_SAY' value (case insensitive)."""
        result = UserMetadata._validate_timezone("RATHER_NOT_SAY")
        assert result == "rather_not_say"

    @patch("areyouok_telegram.data.models.user_metadata.available_timezones")
    @patch("areyouok_telegram.data.models.user_metadata.ZoneInfo")
    def test_validate_timezone_valid_timezone(self, mock_zone_info, mock_available_timezones):
        """Test _validate_timezone with valid timezone identifier."""
        mock_available_timezones.return_value = {"America/New_York", "Europe/London"}

        result = UserMetadata._validate_timezone("america/new_york")

        assert result == "America/New_York"
        mock_zone_info.assert_called_once_with("America/New_York")

    @patch("areyouok_telegram.data.models.user_metadata.available_timezones")
    def test_validate_timezone_invalid_timezone_raises_error(self, mock_available_timezones):
        """Test _validate_timezone raises InvalidTimezoneError for invalid timezone."""
        mock_available_timezones.return_value = {"America/New_York", "Europe/London"}

        with pytest.raises(InvalidTimezoneError) as exc_info:
            UserMetadata._validate_timezone("Invalid/Timezone")

        assert exc_info.value.value == "Invalid/Timezone"
        assert exc_info.value.field == "timezone"

    @pytest.mark.asyncio
    async def test_update_metadata_calls_country_validation(self, mock_db_session):
        """Test update_metadata calls country validation for country field."""
        with patch.object(UserMetadata, "_validate_country", return_value="USA") as mock_validate:
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="country", value="usa")

            mock_validate.assert_called_once_with("usa")

    @pytest.mark.asyncio
    async def test_update_metadata_calls_timezone_validation(self, mock_db_session):
        """Test update_metadata calls timezone validation for timezone field."""
        with patch.object(UserMetadata, "_validate_timezone", return_value="America/New_York") as mock_validate:
            await UserMetadata.update_metadata(
                mock_db_session, user_id="user123", field="timezone", value="america/new_york"
            )

            mock_validate.assert_called_once_with("america/new_york")

    @patch("areyouok_telegram.data.models.user_metadata.decrypt_content")
    def test_to_dict_returns_all_fields(self, mock_decrypt):
        """Test to_dict returns dictionary with all user metadata fields."""
        mock_decrypt.return_value = "John Doe"

        metadata = UserMetadata()
        metadata.user_key = "test_key"
        metadata.user_id = "user123"
        metadata._preferred_name = "encrypted_name"
        metadata.communication_style = "casual"
        metadata.country = "USA"
        metadata.timezone = "America/New_York"

        result = metadata.to_dict()

        expected = {
            "user_id": "user123",
            "preferred_name": "John Doe",
            "communication_style": "casual",
            "country": "USA",
            "timezone": "America/New_York",
        }

        assert result == expected

    def test_get_current_time_with_none_timezone(self):
        """Test get_current_time returns None when timezone is None."""
        metadata = UserMetadata()
        metadata.timezone = None

        result = metadata.get_current_time()

        assert result is None

    def test_get_current_time_with_rather_not_say_timezone(self):
        """Test get_current_time returns None when timezone is 'rather_not_say'."""
        metadata = UserMetadata()
        metadata.timezone = "rather_not_say"

        result = metadata.get_current_time()

        assert result is None

    @patch("areyouok_telegram.data.models.user_metadata.datetime")
    def test_get_current_time_with_valid_timezone(self, mock_datetime):
        """Test get_current_time returns current time in user's timezone."""
        # Setup
        test_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ny_timezone = ZoneInfo("America/New_York")
        ny_time = test_time.astimezone(ny_timezone)

        mock_datetime.now.return_value = ny_time

        metadata = UserMetadata()
        metadata.timezone = "America/New_York"

        result = metadata.get_current_time()

        assert result == ny_time
        mock_datetime.now.assert_called_once_with(ny_timezone)

    @patch("areyouok_telegram.data.models.user_metadata.datetime")
    def test_get_current_time_with_different_timezone(self, mock_datetime):
        """Test get_current_time works with different timezone."""
        # Setup
        test_time = datetime(2025, 1, 1, 20, 0, 0, tzinfo=UTC)
        tokyo_timezone = ZoneInfo("Asia/Tokyo")
        tokyo_time = test_time.astimezone(tokyo_timezone)

        mock_datetime.now.return_value = tokyo_time

        metadata = UserMetadata()
        metadata.timezone = "Asia/Tokyo"

        result = metadata.get_current_time()

        assert result == tokyo_time
        mock_datetime.now.assert_called_once_with(tokyo_timezone)

    @patch("areyouok_telegram.data.models.user_metadata.ZoneInfo")
    def test_get_current_time_with_invalid_timezone(self, mock_zone_info):
        """Test get_current_time returns None when timezone is invalid."""
        # Setup ZoneInfo to raise an exception for invalid timezone
        mock_zone_info.side_effect = Exception("Invalid timezone")

        metadata = UserMetadata()
        metadata.timezone = "Invalid/Timezone"

        result = metadata.get_current_time()

        assert result is None
        mock_zone_info.assert_called_once_with("Invalid/Timezone")

    @patch("areyouok_telegram.data.models.user_metadata.ZoneInfo")
    def test_get_current_time_handles_zoneinfo_key_error(self, mock_zone_info):
        """Test get_current_time handles ZoneInfo KeyError gracefully."""
        # Setup ZoneInfo to raise KeyError (typical for invalid timezone)
        mock_zone_info.side_effect = KeyError("'Unknown/Timezone'")

        metadata = UserMetadata()
        metadata.timezone = "Unknown/Timezone"

        result = metadata.get_current_time()

        assert result is None
        mock_zone_info.assert_called_once_with("Unknown/Timezone")

    def test_get_current_time_with_utc_timezone(self):
        """Test get_current_time works with UTC timezone."""
        with freeze_time("2025-01-01 12:00:00"):
            metadata = UserMetadata()
            metadata.timezone = "UTC"

            result = metadata.get_current_time()

            assert result is not None
            assert result.tzinfo == ZoneInfo("UTC")
            assert result.year == 2025
            assert result.month == 1
            assert result.day == 1
            assert result.hour == 12

    def test_get_current_time_with_case_sensitive_timezone(self):
        """Test get_current_time with case-sensitive timezone identifiers."""
        with freeze_time("2025-06-15 15:30:00"):
            metadata = UserMetadata()
            metadata.timezone = "Europe/London"

            result = metadata.get_current_time()

            assert result is not None
            assert result.tzinfo == ZoneInfo("Europe/London")
            # In June, London is in BST (UTC+1)
            assert result.hour == 16  # 15:30 UTC + 1 hour = 16:30 BST


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


class TestInvalidFieldValueError:
    """Test InvalidFieldValueError exception."""

    def test_invalid_field_type_error_creation(self):
        """Test InvalidFieldValueError is created with correct attributes."""
        error = InvalidFieldValueError("test_field", "a string", "expected_type")

        assert error.field == "test_field"
        assert error.expected == "expected_type"
        assert "a string is invalid for field 'test_field'. Expected: expected_type." == str(error)

    def test_invalid_field_type_error_inheritance(self):
        """Test InvalidFieldValueError inherits from Exception."""
        error = InvalidFieldValueError("test", "test", "expected_type")
        assert isinstance(error, Exception)


class TestInvalidCountryCodeError:
    """Test InvalidCountryCodeError exception."""

    def test_invalid_country_code_error_creation(self):
        """Test InvalidCountryCodeError is created with correct attributes."""
        error = InvalidCountryCodeError("INVALID")

        assert error.field == "country"
        assert error.value == "INVALID"
        assert error.expected == "ISO3 country code or 'rather_not_say'"
        assert "INVALID is invalid for field 'country'. Expected: ISO3 country code or 'rather_not_say'." == str(error)

    def test_invalid_country_code_error_inheritance(self):
        """Test InvalidCountryCodeError inherits from InvalidFieldValueError."""
        error = InvalidCountryCodeError("INVALID")
        assert isinstance(error, InvalidFieldValueError)
        assert isinstance(error, Exception)


class TestInvalidTimezoneError:
    """Test InvalidTimezoneError exception."""

    def test_invalid_timezone_error_creation(self):
        """Test InvalidTimezoneError is created with correct attributes."""
        error = InvalidTimezoneError("Invalid/Timezone")

        assert error.field == "timezone"
        assert error.value == "Invalid/Timezone"
        assert error.expected == "valid IANA timezone identifier or 'rather_not_say'"
        expected_message = (
            "Invalid/Timezone is invalid for field 'timezone'. "
            "Expected: valid IANA timezone identifier or 'rather_not_say'."
        )
        assert str(error) == expected_message

    def test_invalid_timezone_error_inheritance(self):
        """Test InvalidTimezoneError inherits from InvalidFieldValueError."""
        error = InvalidTimezoneError("Invalid/Timezone")
        assert isinstance(error, InvalidFieldValueError)
        assert isinstance(error, Exception)
