import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

import pycountry
from cachetools import TTLCache
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.dialects.postgresql import TIMESTAMP, insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from areyouok_telegram.config import ENV
from areyouok_telegram.data import Base
from areyouok_telegram.encryption import decrypt_content, encrypt_content
from areyouok_telegram.logging import traced

RESPONSE_SPEED_MAP = {
    "fast": 0.0,
    "normal": 2.0,
    "slow": 5.0,
}


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
    """User metadata and preferences stored as encrypted JSON."""

    __tablename__ = "user_metadata"
    __table_args__ = {"schema": ENV}

    # Valid metadata fields
    _VALID_FIELDS = {
        "preferred_name",
        "country",
        "timezone",
        "response_speed",
        "response_speed_adj",
        "communication_style",
    }

    # TTL cache for decrypted metadata (1 hour TTL, max 1000 entries)
    _metadata_cache: TTLCache[str, dict] = TTLCache(maxsize=1000, ttl=1 * 60 * 60)

    user_key = Column(String, nullable=False, unique=True)
    user_id = Column(String, nullable=False, unique=True)
    content = Column(String, nullable=True)  # Stores encrypted JSON string

    # Metadata
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_user_key(user_id: str) -> str:
        """Generate a unique key for user metadata based on their user ID."""
        return hashlib.sha256(f"metadata:{user_id}".encode()).hexdigest()

    def _get_metadata(self) -> dict:
        """Get decrypted metadata from cache or decrypt from database.

        Returns:
            dict: The decrypted metadata dictionary
        """
        # Check cache first
        if self.user_key in self._metadata_cache:
            return self._metadata_cache[self.user_key]

        # Decrypt if not cached and metadata exists
        if self.content:
            decrypted_json = decrypt_content(self.content)
            metadata_dict = json.loads(decrypted_json) if decrypted_json else {}
            self._metadata_cache[self.user_key] = metadata_dict
            return metadata_dict

        return {}

    def _set_metadata(self, metadata_dict: dict):
        """Encrypt and store metadata.

        Args:
            metadata_dict: The metadata dictionary to encrypt and store
        """
        json_str = json.dumps(metadata_dict)
        self.content = encrypt_content(json_str)
        # Update cache
        self._metadata_cache[self.user_key] = metadata_dict

    # Read-only properties for metadata fields
    @property
    def preferred_name(self) -> str | None:
        """Get user's preferred name."""
        return self._get_metadata().get("preferred_name")

    @property
    def country(self) -> str | None:
        """Get user's country."""
        return self._get_metadata().get("country")

    @property
    def timezone(self) -> str | None:
        """Get user's timezone."""
        return self._get_metadata().get("timezone")

    @property
    def response_speed(self) -> str | None:
        """Get user's response speed preference."""
        return self._get_metadata().get("response_speed")

    @property
    def response_speed_adj(self) -> int | None:
        """Get user's response speed adjustment."""
        return self._get_metadata().get("response_speed_adj")

    @property
    def communication_style(self) -> str | None:
        """Get user's communication style preference."""
        return self._get_metadata().get("communication_style")

    @property
    def response_wait_time(self) -> float:
        """Get the user's preferred response wait time in seconds.

        Returns:
            Response wait time in seconds (fast=0, normal=2, slow=5), with adjustment
        """
        response_speed_adj = self.response_speed_adj or 0
        return max(RESPONSE_SPEED_MAP.get(self.response_speed, 2.0) + response_speed_adj, 0)

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
        if field not in cls._VALID_FIELDS:
            valid_fields = list(cls._VALID_FIELDS)
            raise InvalidFieldError(field, valid_fields)

        # Validate and normalize field values
        validated_value = cls.validate_field(field, value)

        now = datetime.now(UTC)
        user_key = cls.generate_user_key(user_id)

        # Get existing metadata or create new
        existing = await cls.get_by_user_id(db_conn, user_id=user_id)

        if existing:
            metadata_dict = existing._get_metadata()
        else:
            metadata_dict = {}

        # Update the field in the dictionary
        if validated_value is None:
            metadata_dict.pop(field, None)
        else:
            metadata_dict[field] = validated_value

        # Encrypt the entire JSON
        encrypted_json = encrypt_content(json.dumps(metadata_dict))

        # Prepare values for database update
        values = {
            "user_key": user_key,
            "user_id": user_id,
            "content": encrypted_json,
            "created_at": now,
            "updated_at": now,
        }

        stmt = pg_insert(cls).values(**values)

        # On conflict, update metadata and updated_at
        update_values = {
            "content": stmt.excluded.content,
            "updated_at": stmt.excluded.updated_at,
        }

        stmt = stmt.on_conflict_do_update(
            index_elements=["user_key"],
            set_=update_values,
        )

        await db_conn.execute(stmt)

        # Return the updated object
        return await cls.get_by_user_id(db_conn, user_id=user_id)

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

    @classmethod
    def validate_field(cls, field: str, value: Any) -> Any:
        """Validate and normalize a field value.

        Args:
            field: Field name to validate
            value: Value to validate

        Returns:
            The validated and normalized value

        Raises:
            InvalidFieldValueError: If value is invalid for the field
        """
        if value is None:
            return None

        if field == "preferred_name":
            if not isinstance(value, str):
                raise InvalidFieldValueError(field, value, "a string or None")
            return value

        elif field == "country":
            if not isinstance(value, str):
                raise InvalidFieldValueError(field, value, "a string or None")

            if value.lower() == "rather_not_say":
                return "rather_not_say"
            else:
                country = pycountry.countries.get(alpha_3=value.upper())
                if country:
                    return value.upper()
            raise InvalidCountryCodeError(value)

        elif field == "timezone":
            if not isinstance(value, str):
                raise InvalidFieldValueError(field, value, "a string or None")

            if value.lower() == "rather_not_say":
                return "rather_not_say"
            else:
                all_timezones = available_timezones()
                for tz in all_timezones:
                    if tz.lower() == value.lower():
                        ZoneInfo(tz)
                        return tz

            raise InvalidTimezoneError(value)

        elif field == "response_speed":
            if not isinstance(value, str):
                raise InvalidFieldValueError(field, value, "a string or None")

            value = value.lower() or "normal"
            if value not in ["fast", "normal", "slow"]:
                raise InvalidFieldValueError(field, value, "one of: 'fast', 'normal', 'slow'")

            return value

        elif field == "response_speed_adj":
            try:
                return int(value)
            except (TypeError, ValueError) as e:
                raise InvalidFieldValueError(field, value, "an integer number of seconds or None") from e

        elif field == "communication_style":
            if not isinstance(value, str):
                raise InvalidFieldValueError(field, value, "a string or None")
            return value

        else:
            return value

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the user metadata."""
        metadata = self._get_metadata()
        return {
            "user_id": self.user_id,
            "preferred_name": metadata.get("preferred_name"),
            "communication_style": metadata.get("communication_style"),
            "response_speed": metadata.get("response_speed"),
            "response_speed_adj": metadata.get("response_speed_adj"),
            "country": metadata.get("country"),
            "timezone": metadata.get("timezone"),
        }
