import hashlib
from datetime import UTC
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo
from zoneinfo import available_timezones

import pycountry
from cachetools import TTLCache
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.encryption import decrypt_content
from areyouok_telegram.encryption import encrypt_content
from areyouok_telegram.utils import traced


class InvalidFieldError(Exception):
    """Raised when an invalid field name is provided."""

    def __init__(self, field: str, valid_fields: list[str]):
        super().__init__(f"Invalid field '{field}'. Valid fields: {valid_fields}")
        self.field = field
        self.valid_fields = valid_fields


class InvalidFieldValueError(Exception):
    """Raised when an invalid type is provided for a field."""

    def __init__(self, field: str, value: Any, expected: str):
        super().__init__(f"{value} is invalid for field '{field}'. Expected: {expected}.")
        self.field = field
        self.value = value
        self.expected = expected


class InvalidCountryCodeError(InvalidFieldValueError):
    """Raised when an invalid country code is provided."""

    def __init__(self, value: str):
        super().__init__(field="country", value=value, expected="ISO3 country code or 'rather_not_say'")


class InvalidTimezoneError(InvalidFieldValueError):
    """Raised when an invalid timezone is provided."""

    def __init__(self, value: str):
        super().__init__(field="timezone", value=value, expected="valid IANA timezone identifier or 'rather_not_say'")


class UserMetadata(Base):
    """User metadata and preferences with selective field encryption."""

    __tablename__ = "user_metadata"
    __table_args__ = {"schema": ENV}

    # Field mappings for validation
    _ENCRYPTED_FIELDS = {
        "preferred_name": "_preferred_name",
    }

    _UNENCRYPTED_FIELDS = {
        "country": "country",
        "timezone": "timezone",
        "communication_style": "communication_style",
    }

    # TTL cache for decrypted fields (1 hour TTL, max 1000 entries)
    _field_cache: TTLCache[str, str] = TTLCache(maxsize=1000, ttl=1 * 60 * 60)

    user_key = Column(String, nullable=False, unique=True)
    user_id = Column(String, nullable=False, unique=True)

    _preferred_name = Column(String, nullable=True)

    country = Column(String, nullable=True)
    timezone = Column(String, nullable=True)

    communication_style = Column(String, nullable=True)

    # Metadata
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_user_key(user_id: str) -> str:
        """Generate a unique key for user metadata based on their user ID."""
        return hashlib.sha256(f"metadata:{user_id}".encode()).hexdigest()

    # Read-only properties for encrypted fields
    @property
    def preferred_name(self) -> str | None:
        """Get user's preferred name."""
        return self._decrypt_field("preferred_name", self._preferred_name)

    @property
    def country_display_name(self) -> str | None:
        """Get user's country as a full country name instead of ISO3 code.

        Returns:
            Full country name, "Prefer not to say", or None if not set
        """
        if not self.country:
            return None

        if self.country == "rather_not_say":
            return "Prefer not to say"

        try:
            country = pycountry.countries.get(alpha_3=self.country.upper())
        except (AttributeError, LookupError):
            return self.country
        else:
            return country.name if country else self.country

    @classmethod
    @traced(extract_args=["user_id", "field"])
    async def update_metadata(
        cls,
        db_conn: AsyncSession,
        *,
        user_id: str,
        field: str,
        value: Any,
    ) -> "UserMetadata":
        """Update a single metadata field for a user.

        Args:
            db_conn: Database connection
            user_id: User ID to update
            field: Field name to update
            value: New value for the field

        Returns:
            UserMetadata: Updated user metadata object

        Raises:
            InvalidFieldError: If field name is invalid
            InvalidFieldValueError: If value provided is incorrect for the field
        """
        # Validate field name
        if field not in cls._ENCRYPTED_FIELDS and field not in cls._UNENCRYPTED_FIELDS:
            valid_fields = list(cls._ENCRYPTED_FIELDS.keys()) + list(cls._UNENCRYPTED_FIELDS.keys())
            raise InvalidFieldError(field, valid_fields)

        # Validate and normalize field values
        if value is not None:  # Allow None for clearing fields
            # Validate encrypted field types (must be strings)
            if field in cls._ENCRYPTED_FIELDS and not isinstance(value, str):
                raise InvalidFieldValueError(field, value, "a string or None")
            if field == "country":
                value = cls._validate_country(value)
            elif field == "timezone":
                value = cls._validate_timezone(value)

        now = datetime.now(UTC)
        user_key = cls.generate_user_key(user_id)

        # Prepare values for database update
        values = {
            "user_key": user_key,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }

        # Handle encrypted fields
        if field in cls._ENCRYPTED_FIELDS:
            db_field = cls._ENCRYPTED_FIELDS[field]
            values[db_field] = encrypt_content(value) if value is not None else None
        # Handle unencrypted fields
        elif field in cls._UNENCRYPTED_FIELDS:
            db_field = cls._UNENCRYPTED_FIELDS[field]
            values[db_field] = value

        stmt = pg_insert(cls).values(**values)

        # On conflict, only update the specific field being changed and updated_at
        update_values = {"updated_at": stmt.excluded.updated_at}

        # Add the specific field being updated
        if field in cls._ENCRYPTED_FIELDS:
            db_field = cls._ENCRYPTED_FIELDS[field]
            update_values[db_field] = stmt.excluded[db_field]
        elif field in cls._UNENCRYPTED_FIELDS:
            db_field = cls._UNENCRYPTED_FIELDS[field]
            update_values[db_field] = stmt.excluded[db_field]

        stmt = stmt.on_conflict_do_update(
            index_elements=["user_key"],
            set_=update_values,
        )

        await db_conn.execute(stmt)

    @classmethod
    async def get_by_user_id(
        cls,
        db_conn: AsyncSession,
        *,
        user_id: str,
    ) -> "UserMetadata | None":
        """Retrieve user metadata by user ID."""
        stmt = select(cls).where(cls.user_id == user_id)
        result = await db_conn.execute(stmt)
        return result.scalars().first()

    @staticmethod
    def _validate_country(value: str) -> str:
        """Validate country field.

        Args:
            value: Country code or special value

        Returns:
            The validated country value

        Raises:
            InvalidCountryCodeError: If the country code is invalid
        """
        # Allow special value for privacy
        if value.lower() == "rather_not_say":
            return "rather_not_say"

        # Check for valid ISO3 country code
        country = pycountry.countries.get(alpha_3=value.upper())
        if country:
            return value.upper()

        raise InvalidCountryCodeError(value)

    @staticmethod
    def _validate_timezone(value: str) -> str:
        """Validate timezone field.

        Args:
            value: Timezone identifier

        Returns:
            The validated timezone value

        Raises:
            InvalidTimezoneError: If the timezone is invalid
        """
        if value.lower() == "rather_not_say":
            return "rather_not_say"

        all_timezones = available_timezones()

        for tz in all_timezones:
            if tz.lower() == value.lower():
                ZoneInfo(tz)
                return tz

        raise InvalidTimezoneError(value)

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the user metadata."""
        return {
            "user_id": self.user_id,
            "preferred_name": self.preferred_name,
            "communication_style": self.communication_style,
            "country": self.country,
            "timezone": self.timezone,
        }

    def get_current_time(self) -> datetime | None:
        """Get the current time in the user's timezone.

        Returns:
            datetime: Current time in user's timezone, or None if timezone is not set or is 'rather_not_say'
        """
        if self.timezone is None or self.timezone == "rather_not_say":
            return None

        try:
            user_tz = ZoneInfo(self.timezone)
            return datetime.now(user_tz)
        except Exception:
            # If timezone is invalid, return None
            return None

    def _decrypt_field(self, field_name: str, encrypted_value: str) -> str | None:
        """Decrypt a field value with caching.

        Args:
            field_name: Name of the field (for caching)
            encrypted_value: Encrypted value to decrypt

        Returns:
            str: The decrypted value, or None if encrypted_value is None
        """
        if encrypted_value is None:
            return None

        cache_key = f"{self.user_key}:{field_name}"

        # Check cache first
        cached_value = self._field_cache.get(cache_key)
        if cached_value is not None:
            return cached_value

        # Decrypt and cache
        decrypted_value = decrypt_content(encrypted_value)
        if decrypted_value is not None:
            self._field_cache[cache_key] = decrypted_value

        return decrypted_value
