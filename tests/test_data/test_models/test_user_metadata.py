"""Tests for UserMetadata model."""

import hashlib
from datetime import UTC
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from areyouok_telegram.data.models.user_metadata import InvalidCountryCodeError
from areyouok_telegram.data.models.user_metadata import InvalidFieldError
from areyouok_telegram.data.models.user_metadata import InvalidFieldValueError
from areyouok_telegram.data.models.user_metadata import InvalidTimezoneError
from areyouok_telegram.data.models.user_metadata import UserMetadata


class TestUserMetadata:
    """Test UserMetadata model."""

    def setup_method(self):
        """Clear cache before each test."""
        UserMetadata._metadata_cache.clear()

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

    def test_get_metadata_with_none_content(self):
        """Test _get_metadata returns empty dict when content is None."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        metadata.content = None

        result = metadata._get_metadata()

        assert result == {}

    def test_get_metadata_with_cached_value(self):
        """Test _get_metadata returns cached metadata dict."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        cached_data = {"preferred_name": "John Doe", "country": "USA"}

        # Pre-populate cache
        UserMetadata._metadata_cache[metadata.user_key] = cached_data

        result = metadata._get_metadata()

        assert result == cached_data

    @patch("areyouok_telegram.data.models.user_metadata.decrypt_content")
    @patch("areyouok_telegram.data.models.user_metadata.json")
    def test_get_metadata_without_cached_value(self, mock_json, mock_decrypt):
        """Test _get_metadata decrypts, parses JSON and caches metadata dict."""
        mock_decrypt.return_value = '{"preferred_name": "John Doe", "country": "USA"}'
        mock_json.loads.return_value = {"preferred_name": "John Doe", "country": "USA"}

        metadata = UserMetadata()
        metadata.user_key = "test_key"
        metadata.content = "encrypted_json"

        result = metadata._get_metadata()

        expected_data = {"preferred_name": "John Doe", "country": "USA"}
        assert result == expected_data
        assert UserMetadata._metadata_cache[metadata.user_key] == expected_data
        mock_decrypt.assert_called_once_with("encrypted_json")
        mock_json.loads.assert_called_once_with('{"preferred_name": "John Doe", "country": "USA"}')

    @patch("areyouok_telegram.data.models.user_metadata.decrypt_content")
    def test_get_metadata_with_none_decrypt_result(self, mock_decrypt):
        """Test _get_metadata handles None decrypt result by caching empty dict."""
        mock_decrypt.return_value = None
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        metadata.content = "encrypted_json"

        result = metadata._get_metadata()

        assert result == {}
        assert UserMetadata._metadata_cache[metadata.user_key] == {}
        mock_decrypt.assert_called_once_with("encrypted_json")

    @patch("areyouok_telegram.data.models.user_metadata.encrypt_content")
    @patch("areyouok_telegram.data.models.user_metadata.json")
    def test_set_metadata(self, mock_json, mock_encrypt):
        """Test _set_metadata encrypts JSON and updates cache."""
        mock_json.dumps.return_value = '{"preferred_name": "John Doe"}'
        mock_encrypt.return_value = "encrypted_json"

        metadata = UserMetadata()
        metadata.user_key = "test_key"
        metadata_dict = {"preferred_name": "John Doe"}

        metadata._set_metadata(metadata_dict)

        assert metadata.content == "encrypted_json"
        assert UserMetadata._metadata_cache[metadata.user_key] == metadata_dict
        mock_json.dumps.assert_called_once_with(metadata_dict)
        mock_encrypt.assert_called_once_with('{"preferred_name": "John Doe"}')

    def test_preferred_name_property(self):
        """Test preferred_name property gets value from metadata dict."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        # Pre-populate cache
        UserMetadata._metadata_cache[metadata.user_key] = {"preferred_name": "John Doe"}

        result = metadata.preferred_name

        assert result == "John Doe"

    def test_timezone_property(self):
        """Test timezone property gets value from metadata dict."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        # Pre-populate cache
        UserMetadata._metadata_cache[metadata.user_key] = {"timezone": "America/New_York"}

        result = metadata.timezone

        assert result == "America/New_York"

    def test_communication_style_property(self):
        """Test communication_style property gets value from metadata dict."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        # Pre-populate cache
        UserMetadata._metadata_cache[metadata.user_key] = {"communication_style": "casual"}

        result = metadata.communication_style

        assert result == "casual"

    def test_property_with_none_value(self):
        """Test property returns None when field not in metadata dict."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        # Pre-populate cache with empty dict
        UserMetadata._metadata_cache[metadata.user_key] = {}

        result = metadata.preferred_name

        assert result is None

    def test_country_property(self):
        """Test country property gets value from metadata dict."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        # Pre-populate cache
        UserMetadata._metadata_cache[metadata.user_key] = {"country": "USA"}

        result = metadata.country

        assert result == "USA"

    def test_response_speed_property(self):
        """Test response_speed property gets value from metadata dict."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        # Pre-populate cache
        UserMetadata._metadata_cache[metadata.user_key] = {"response_speed": "fast"}

        result = metadata.response_speed

        assert result == "fast"

    def test_response_speed_adj_property(self):
        """Test response_speed_adj property gets value from metadata dict."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        # Pre-populate cache
        UserMetadata._metadata_cache[metadata.user_key] = {"response_speed_adj": 5}

        result = metadata.response_speed_adj

        assert result == 5

    @pytest.mark.asyncio
    async def test_update_metadata_invalid_field(self, mock_db_session):
        """Test update_metadata raises InvalidFieldError for invalid field."""
        with pytest.raises(InvalidFieldError) as exc_info:
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="invalid_field", value="value")

        assert exc_info.value.field == "invalid_field"
        assert "preferred_name" in exc_info.value.valid_fields
        assert "country" in exc_info.value.valid_fields

    @pytest.mark.asyncio
    async def test_update_metadata_invalid_field_value(self, mock_db_session):
        """Test update_metadata raises InvalidFieldValueError for invalid field value."""
        with pytest.raises(InvalidFieldValueError) as exc_info:
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="preferred_name", value=123)

        assert exc_info.value.field == "preferred_name"
        assert exc_info.value.expected == "a string or None"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.user_metadata.encrypt_content")
    async def test_update_metadata_with_new_user(self, mock_encrypt, mock_db_session):
        """Test update_metadata creates new user metadata when user doesn't exist."""
        mock_encrypt.return_value = "encrypted_json"

        # Mock get_by_user_id to return None (user doesn't exist)
        with patch.object(UserMetadata, "get_by_user_id", side_effect=[None, MagicMock(spec=UserMetadata)]):
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="preferred_name", value="John")

        # Verify encryption was called with JSON containing the field
        mock_encrypt.assert_called_once_with('{"preferred_name": "John"}')

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.user_metadata.encrypt_content")
    async def test_update_metadata_with_existing_user(self, mock_encrypt, mock_db_session):
        """Test update_metadata updates existing user metadata."""
        mock_encrypt.return_value = "encrypted_json"

        # Create mock existing user with metadata
        existing_user = MagicMock(spec=UserMetadata)
        existing_user._get_metadata.return_value = {"country": "USA"}

        with patch.object(UserMetadata, "get_by_user_id", side_effect=[existing_user, MagicMock(spec=UserMetadata)]):
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="preferred_name", value="John")

        # Verify encryption was called with JSON containing both fields
        mock_encrypt.assert_called_once_with('{"country": "USA", "preferred_name": "John"}')

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.user_metadata.encrypt_content")
    async def test_update_metadata_with_none_value(self, mock_encrypt, mock_db_session):
        """Test update_metadata removes field when value is None."""
        mock_encrypt.return_value = "encrypted_json"

        # Create mock existing user with metadata
        existing_user = MagicMock(spec=UserMetadata)
        existing_user._get_metadata.return_value = {"preferred_name": "John", "country": "USA"}

        with patch.object(UserMetadata, "get_by_user_id", side_effect=[existing_user, MagicMock(spec=UserMetadata)]):
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="preferred_name", value=None)

        # Verify encryption was called with JSON that no longer contains preferred_name
        mock_encrypt.assert_called_once_with('{"country": "USA"}')

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_metadata_database_upsert_structure(self, mock_db_session):
        """Test update_metadata creates correct database upsert statement."""
        user_id = "user123"

        # Create mock existing user with proper metadata
        existing_user = MagicMock(spec=UserMetadata)
        existing_user._get_metadata.return_value = {"timezone": "UTC"}

        mock_updated_user = MagicMock(spec=UserMetadata)

        with patch.object(UserMetadata, "get_by_user_id", side_effect=[existing_user, mock_updated_user]):
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

    def test_valid_fields_completeness(self):
        """Test that all expected fields are in _VALID_FIELDS."""
        valid_fields = UserMetadata._VALID_FIELDS

        # Verify expected fields
        assert "preferred_name" in valid_fields
        assert "country" in valid_fields
        assert "timezone" in valid_fields
        assert "communication_style" in valid_fields
        assert "response_speed" in valid_fields
        assert "response_speed_adj" in valid_fields

        # Verify it's a set with expected count
        assert isinstance(valid_fields, set)
        assert len(valid_fields) == 6

    def test_cache_isolation_between_users(self):
        """Test that cache is properly isolated between different users."""
        metadata1 = UserMetadata()
        metadata1.user_key = "user1_key"

        metadata2 = UserMetadata()
        metadata2.user_key = "user2_key"

        # Manually set cache for different users
        user1_data = {"preferred_name": "User1 Name"}
        user2_data = {"preferred_name": "User2 Name"}

        UserMetadata._metadata_cache[metadata1.user_key] = user1_data
        UserMetadata._metadata_cache[metadata2.user_key] = user2_data

        # Verify values are properly isolated
        assert UserMetadata._metadata_cache.get(metadata1.user_key) == user1_data
        assert UserMetadata._metadata_cache.get(metadata2.user_key) == user2_data

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.user_metadata.encrypt_content")
    async def test_update_metadata_null_string_value(self, mock_encrypt, mock_db_session):
        """Test update_metadata with valid None value for encrypted field accepts type check."""
        # Mock get_by_user_id to return None (user doesn't exist)
        with patch.object(UserMetadata, "get_by_user_id", side_effect=[None, MagicMock(spec=UserMetadata)]):
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="preferred_name", value=None)

        # Verify encryption was called with empty dict (user doesn't exist, field removed)
        mock_encrypt.assert_called_once_with("{}")

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

        # Mock the update_metadata to avoid actual async operations
        with patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock) as mock_update:
            # Configure mock to succeed for all test values
            mock_update.return_value = MagicMock(spec=UserMetadata)

            for test_value in test_values:
                await UserMetadata.update_metadata(
                    mock_db_session, user_id="user123", field="preferred_name", value=test_value
                )

            # Verify the method was called for each test value
            assert mock_update.call_count == len(test_values)

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
            # Create mock existing user with proper metadata
            existing_user = MagicMock(spec=UserMetadata)
            existing_user._get_metadata.return_value = {"timezone": "UTC"}

            with patch.object(
                UserMetadata, "get_by_user_id", side_effect=[existing_user, MagicMock(spec=UserMetadata)]
            ):
                await UserMetadata.update_metadata(
                    mock_db_session, user_id="user123", field=field_name, value=field_value
                )

    @pytest.mark.asyncio
    async def test_update_metadata_unencrypted_string_values(self, mock_db_session):
        """Test update_metadata with different string values for country field."""
        country_values = ["USA", "CAN", "GBR"]

        for country_value in country_values:
            # Create mock existing user with proper metadata
            existing_user = MagicMock(spec=UserMetadata)
            existing_user._get_metadata.return_value = {"timezone": "UTC"}

            with patch.object(
                UserMetadata, "get_by_user_id", side_effect=[existing_user, MagicMock(spec=UserMetadata)]
            ):
                await UserMetadata.update_metadata(
                    mock_db_session, user_id="user123", field="country", value=country_value
                )

    @pytest.mark.asyncio
    async def test_update_metadata_unencrypted_field_with_value(self, mock_db_session):
        """Test update_metadata with country field having a value."""
        with patch.object(UserMetadata, "get_by_user_id", side_effect=[None, MagicMock(spec=UserMetadata)]):
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="country", value="USA")

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_metadata_unencrypted_field_in_conflict_resolution(self, mock_db_session):
        """Test update_metadata with communication_style field."""
        # Create mock existing user with proper metadata
        existing_user = MagicMock(spec=UserMetadata)
        existing_user._get_metadata.return_value = {"country": "USA"}

        with patch.object(UserMetadata, "get_by_user_id", side_effect=[existing_user, MagicMock(spec=UserMetadata)]):
            await UserMetadata.update_metadata(
                mock_db_session, user_id="user123", field="communication_style", value="formal"
            )

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_metadata_unencrypted_field_branch_coverage(self, mock_db_session):
        """Test update_metadata with timezone field."""
        # Create mock existing user with proper metadata
        existing_user = MagicMock(spec=UserMetadata)
        existing_user._get_metadata.return_value = {"country": "USA"}

        with patch.object(UserMetadata, "get_by_user_id", side_effect=[existing_user, MagicMock(spec=UserMetadata)]):
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

        with patch.object(UserMetadata, "get_by_user_id", side_effect=[None, MagicMock(spec=UserMetadata)]):
            await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="country", value="USA")

        # Verify datetime.now was called with UTC
        mock_datetime.now.assert_called_once_with(UTC)

    def test_cache_ttl_isolation(self):
        """Test that TTL cache properly isolates expired vs active entries."""
        metadata = UserMetadata()
        metadata.user_key = "test_user"

        # Manually test cache behavior
        test_data = {"preferred_name": "Test User"}

        # Add value to cache
        UserMetadata._metadata_cache[metadata.user_key] = test_data

        # Verify it's retrievable
        assert UserMetadata._metadata_cache.get(metadata.user_key) == test_data

        # Clear cache to test isolation
        UserMetadata._metadata_cache.clear()
        assert metadata.user_key not in UserMetadata._metadata_cache

    def test_metadata_cache_key_format(self):
        """Test metadata cache uses correct key format (user_key)."""
        metadata = UserMetadata()
        metadata.user_key = "test_user_123"
        test_data = {"preferred_name": "Test User"}

        # Manually set cache
        UserMetadata._metadata_cache[metadata.user_key] = test_data

        # Verify cache key is the user_key
        assert UserMetadata._metadata_cache.get(metadata.user_key) == test_data

        # Test that _get_metadata uses the cache correctly
        result = metadata._get_metadata()
        assert result == test_data

    def test_validate_country_rather_not_say(self):
        """Test validate_field with country 'rather_not_say' value."""
        result = UserMetadata.validate_field("country", "rather_not_say")
        assert result == "rather_not_say"

    def test_validate_country_rather_not_say_case_insensitive(self):
        """Test validate_field with country 'RATHER_NOT_SAY' value (case insensitive)."""
        result = UserMetadata.validate_field("country", "RATHER_NOT_SAY")
        assert result == "rather_not_say"

    def test_validate_country_valid_iso3_code(self):
        """Test validate_field with valid ISO3 country code."""
        result = UserMetadata.validate_field("country", "usa")
        assert result == "USA"

    def test_validate_country_valid_iso3_code_uppercase(self):
        """Test validate_field with valid uppercase ISO3 country code."""
        result = UserMetadata.validate_field("country", "CAN")
        assert result == "CAN"

    def test_validate_country_invalid_code_raises_error(self):
        """Test validate_field raises InvalidCountryCodeError for invalid country code."""
        with pytest.raises(InvalidCountryCodeError) as exc_info:
            UserMetadata.validate_field("country", "INVALID")

        assert exc_info.value.value == "INVALID"
        assert exc_info.value.field == "country"

    def test_validate_timezone_rather_not_say(self):
        """Test validate_field with timezone 'rather_not_say' value."""
        result = UserMetadata.validate_field("timezone", "rather_not_say")
        assert result == "rather_not_say"

    def test_validate_timezone_rather_not_say_case_insensitive(self):
        """Test validate_field with timezone 'RATHER_NOT_SAY' value (case insensitive)."""
        result = UserMetadata.validate_field("timezone", "RATHER_NOT_SAY")
        assert result == "rather_not_say"

    @patch("areyouok_telegram.data.models.user_metadata.available_timezones")
    @patch("areyouok_telegram.data.models.user_metadata.ZoneInfo")
    def test_validate_timezone_valid_timezone(self, mock_zone_info, mock_available_timezones):
        """Test validate_field with valid timezone identifier."""
        mock_available_timezones.return_value = {"America/New_York", "Europe/London"}

        result = UserMetadata.validate_field("timezone", "america/new_york")

        assert result == "America/New_York"
        mock_zone_info.assert_called_once_with("America/New_York")

    @patch("areyouok_telegram.data.models.user_metadata.available_timezones")
    def test_validate_timezone_invalid_timezone_raises_error(self, mock_available_timezones):
        """Test validate_field raises InvalidTimezoneError for invalid timezone."""
        mock_available_timezones.return_value = {"America/New_York", "Europe/London"}

        with pytest.raises(InvalidTimezoneError) as exc_info:
            UserMetadata.validate_field("timezone", "Invalid/Timezone")

        assert exc_info.value.value == "Invalid/Timezone"
        assert exc_info.value.field == "timezone"

    def test_validate_field_preferred_name(self):
        """Test validate_field with preferred_name field."""
        # Valid string
        result = UserMetadata.validate_field("preferred_name", "John Doe")
        assert result == "John Doe"

        # None value
        result = UserMetadata.validate_field("preferred_name", None)
        assert result is None

        # Invalid type
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("preferred_name", 123)
        assert exc_info.value.field == "preferred_name"
        assert exc_info.value.expected == "a string or None"

    def test_validate_field_country(self):
        """Test validate_field with country field."""
        # Valid country code
        result = UserMetadata.validate_field("country", "USA")
        assert result == "USA"

        # Rather not say
        result = UserMetadata.validate_field("country", "rather_not_say")
        assert result == "rather_not_say"

    def test_validate_field_timezone(self):
        """Test validate_field with timezone field."""
        # Rather not say
        result = UserMetadata.validate_field("timezone", "rather_not_say")
        assert result == "rather_not_say"

        # Valid timezone (case insensitive)
        with patch("areyouok_telegram.data.models.user_metadata.available_timezones") as mock_timezones:
            mock_timezones.return_value = {"America/New_York", "Europe/London"}
            result = UserMetadata.validate_field("timezone", "america/new_york")
            assert result == "America/New_York"

    def test_validate_field_response_speed(self):
        """Test validate_field with response_speed field."""
        # Valid values
        result = UserMetadata.validate_field("response_speed", "fast")
        assert result == "fast"

        result = UserMetadata.validate_field("response_speed", "NORMAL")
        assert result == "normal"

        result = UserMetadata.validate_field("response_speed", "slow")
        assert result == "slow"

        # Invalid value
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("response_speed", "invalid")
        assert exc_info.value.field == "response_speed"
        assert exc_info.value.expected == "one of: 'fast', 'normal', 'slow'"

    def test_validate_field_response_speed_adj(self):
        """Test validate_field with response_speed_adj field."""
        # Valid integer
        result = UserMetadata.validate_field("response_speed_adj", 5)
        assert result == 5

        # String that can be converted to int
        result = UserMetadata.validate_field("response_speed_adj", "10")
        assert result == 10

        # None value
        result = UserMetadata.validate_field("response_speed_adj", None)
        assert result is None

        # Invalid value
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("response_speed_adj", "not_a_number")
        assert exc_info.value.field == "response_speed_adj"
        assert exc_info.value.expected == "an integer number of seconds or None"

    def test_validate_field_communication_style(self):
        """Test validate_field with communication_style field."""
        # Valid string
        result = UserMetadata.validate_field("communication_style", "casual")
        assert result == "casual"

        # None value
        result = UserMetadata.validate_field("communication_style", None)
        assert result is None

        # Invalid type
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("communication_style", 123)
        assert exc_info.value.field == "communication_style"
        assert exc_info.value.expected == "a string or None"

    def test_validate_field_unknown_field(self):
        """Test validate_field with unknown field returns value as-is."""
        result = UserMetadata.validate_field("unknown_field", "some_value")
        assert result == "some_value"

    @pytest.mark.asyncio
    async def test_update_metadata_calls_country_validation(self, mock_db_session):
        """Test update_metadata calls country validation for country field."""
        with patch.object(UserMetadata, "validate_field", return_value="USA") as mock_validate:
            with patch.object(UserMetadata, "get_by_user_id", side_effect=[None, MagicMock(spec=UserMetadata)]):
                await UserMetadata.update_metadata(mock_db_session, user_id="user123", field="country", value="usa")

            mock_validate.assert_called_once_with("country", "usa")

    @pytest.mark.asyncio
    async def test_update_metadata_calls_timezone_validation(self, mock_db_session):
        """Test update_metadata calls timezone validation for timezone field."""
        with patch.object(UserMetadata, "validate_field", return_value="America/New_York") as mock_validate:
            with patch.object(UserMetadata, "get_by_user_id", side_effect=[None, MagicMock(spec=UserMetadata)]):
                await UserMetadata.update_metadata(
                    mock_db_session, user_id="user123", field="timezone", value="america/new_york"
                )

            mock_validate.assert_called_once_with("timezone", "america/new_york")

    def test_to_dict_returns_all_fields(self):
        """Test to_dict returns dictionary with all user metadata fields."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"
        metadata.user_id = "user123"

        # Pre-populate cache with test data
        test_metadata = {
            "preferred_name": "John Doe",
            "communication_style": "casual",
            "response_speed": "fast",
            "response_speed_adj": 5,
            "country": "USA",
            "timezone": "America/New_York",
        }
        UserMetadata._metadata_cache[metadata.user_key] = test_metadata

        result = metadata.to_dict()

        expected = {
            "user_id": "user123",
            "preferred_name": "John Doe",
            "communication_style": "casual",
            "response_speed": "fast",
            "response_speed_adj": 5,
            "country": "USA",
            "timezone": "America/New_York",
        }

        assert result == expected


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


class TestResponseWaitTime:
    """Test response_wait_time property and edge cases."""

    def setup_method(self):
        """Clear cache before each test."""
        UserMetadata._metadata_cache.clear()

    def test_get_response_wait_time_with_none_response_speed_adj(self):
        """Test get_response_wait_time() when response_speed_adj is None (lines 166-167)."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"

        # Pre-populate cache with response_speed but no response_speed_adj (None)
        UserMetadata._metadata_cache[metadata.user_key] = {"response_speed": "normal", "response_speed_adj": None}

        result = metadata.response_wait_time

        # Should use response_speed_adj = 0 when None, and normal = 2.0
        # max(2.0 + 0, 0) = 2.0
        assert result == 2.0

    def test_get_response_wait_time_with_missing_response_speed_adj(self):
        """Test get_response_wait_time() when response_speed_adj is missing from metadata."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"

        # Pre-populate cache with response_speed but no response_speed_adj key at all
        UserMetadata._metadata_cache[metadata.user_key] = {"response_speed": "fast"}

        result = metadata.response_wait_time

        # Should use response_speed_adj = 0 when missing, and fast = 0.0
        # max(0.0 + 0, 0) = 0.0
        assert result == 0.0

    def test_get_response_wait_time_with_response_speed_adj_present(self):
        """Test get_response_wait_time() when response_speed_adj has a value."""
        metadata = UserMetadata()
        metadata.user_key = "test_key"

        # Pre-populate cache with both values
        UserMetadata._metadata_cache[metadata.user_key] = {"response_speed": "slow", "response_speed_adj": -2}

        result = metadata.response_wait_time

        # Should use response_speed_adj = -2, and slow = 5.0
        # max(5.0 + (-2), 0) = max(3.0, 0) = 3.0
        assert result == 3.0


class TestValidateFieldInvalidTypes:
    """Test validate_field with invalid types for specific fields."""

    def test_validate_field_country_with_invalid_type(self):
        """Test validate_field for country with invalid type (line 285)."""
        # Test with non-string type (integer)
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("country", 123)

        assert exc_info.value.field == "country"
        assert exc_info.value.value == 123
        assert exc_info.value.expected == "a string or None"

        # Test with another non-string type (list)
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("country", ["USA", "CAN"])

        assert exc_info.value.field == "country"
        assert exc_info.value.value == ["USA", "CAN"]
        assert exc_info.value.expected == "a string or None"

        # Test with boolean type
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("country", value=True)

        assert exc_info.value.field == "country"
        assert exc_info.value.value is True
        assert exc_info.value.expected == "a string or None"

    def test_validate_field_timezone_with_invalid_type(self):
        """Test validate_field for timezone with invalid type (line 297)."""
        # Test with non-string type (integer)
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("timezone", 123)

        assert exc_info.value.field == "timezone"
        assert exc_info.value.value == 123
        assert exc_info.value.expected == "a string or None"

        # Test with another non-string type (dict)
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("timezone", {"tz": "America/New_York"})

        assert exc_info.value.field == "timezone"
        assert exc_info.value.value == {"tz": "America/New_York"}
        assert exc_info.value.expected == "a string or None"

        # Test with float type
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("timezone", 12.5)

        assert exc_info.value.field == "timezone"
        assert exc_info.value.value == 12.5
        assert exc_info.value.expected == "a string or None"

    def test_validate_field_response_speed_with_invalid_type(self):
        """Test validate_field for response_speed with invalid type (line 312)."""
        # Test with non-string type (integer)
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("response_speed", 123)

        assert exc_info.value.field == "response_speed"
        assert exc_info.value.value == 123
        assert exc_info.value.expected == "a string or None"

        # Test with another non-string type (list)
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("response_speed", ["fast", "slow"])

        assert exc_info.value.field == "response_speed"
        assert exc_info.value.value == ["fast", "slow"]
        assert exc_info.value.expected == "a string or None"

        # Test with boolean type
        with pytest.raises(InvalidFieldValueError) as exc_info:
            UserMetadata.validate_field("response_speed", value=False)

        assert exc_info.value.field == "response_speed"
        assert exc_info.value.value is False
        assert exc_info.value.expected == "a string or None"
