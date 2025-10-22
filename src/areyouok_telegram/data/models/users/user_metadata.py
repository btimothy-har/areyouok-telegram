"""UserMetadata Pydantic model for user preferences and settings."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

import pycountry
import pydantic
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from areyouok_telegram.data.database import async_database
from areyouok_telegram.data.database.schemas import UserMetadataTable
from areyouok_telegram.encryption import decrypt_content, encrypt_content
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import db_retry

RESPONSE_SPEED_MAP = {
    "fast": 0.0,
    "normal": 2.0,
    "slow": 5.0,
}


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


class UserMetadata(pydantic.BaseModel):
    """User metadata and preferences."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    # Required fields
    user_id: int

    # Optional fields
    id: int = 0
    preferred_name: str | None = None
    country: str = pydantic.Field(default="rather_not_say")
    timezone: str = pydantic.Field(default="rather_not_say")
    response_speed: str = pydantic.Field(default="normal")
    response_speed_adj: int = 0
    communication_style: str | None = None
    created_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = pydantic.Field(default_factory=lambda: datetime.now(UTC))

    @pydantic.field_validator("response_speed")
    @classmethod
    def validate_response_speed_field(cls, v: str | None) -> str:
        """Validate response_speed field."""
        if v is None:
            return "normal"
        v = v.lower()
        if v not in ["fast", "normal", "slow"]:
            raise InvalidFieldValueError("response_speed", v, "one of: 'fast', 'normal', 'slow'")
        return v

    @pydantic.field_validator("country")
    @classmethod
    def validate_country_field(cls, v: str) -> str:
        """Validate country field."""
        if v.lower() == "rather_not_say":
            return "rather_not_say"
        country = pycountry.countries.get(alpha_3=v.upper())
        if not country:
            raise InvalidCountryCodeError(v)
        return v.upper()

    @pydantic.field_validator("timezone")
    @classmethod
    def validate_timezone_field(cls, v: str) -> str:
        """Validate timezone field."""
        if v.lower() == "rather_not_say":
            return "rather_not_say"
        all_timezones = available_timezones()
        for tz in all_timezones:
            if tz.lower() == v.lower():
                ZoneInfo(tz)  # Validate it's a real timezone
                return tz
        raise InvalidTimezoneError(v)

    @property
    def object_key(self) -> str:
        """Generate a unique object key for user metadata based on user ID."""
        return hashlib.sha256(f"metadata:{self.user_id}".encode()).hexdigest()

    @staticmethod
    def decrypt_metadata(encrypted_content: str) -> dict:
        """Decrypt metadata content.

        Args:
            encrypted_content: The encrypted JSON string

        Returns:
            Dictionary of metadata fields
        """
        decrypted_json = decrypt_content(encrypted_content)
        return json.loads(decrypted_json) if decrypted_json else {}

    def encrypt_metadata(self) -> str:
        """Encrypt metadata fields into a JSON string.

        Returns:
            Encrypted JSON string
        """
        metadata_dict = {
            "preferred_name": self.preferred_name,
            "country": self.country,
            "timezone": self.timezone,
            "response_speed": self.response_speed,
            "response_speed_adj": self.response_speed_adj,
            "communication_style": self.communication_style,
        }
        # Remove None values
        metadata_dict = {k: v for k, v in metadata_dict.items() if v is not None}
        return encrypt_content(json.dumps(metadata_dict))

    @property
    def response_wait_time(self) -> float:
        """Get the user's preferred response wait time in seconds.

        Returns:
            Response wait time in seconds (fast=0, normal=2, slow=5), with adjustment
        """
        return max(RESPONSE_SPEED_MAP.get(self.response_speed, 2.0) + self.response_speed_adj, 0)

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the user metadata."""
        return {
            "user_id": self.user_id,
            "preferred_name": self.preferred_name,
            "communication_style": self.communication_style,
            "response_speed": self.response_speed,
            "response_speed_adj": self.response_speed_adj,
            "country": self.country,
            "timezone": self.timezone,
        }

    @traced(extract_args=["user_id"])
    @db_retry()
    async def save(self) -> UserMetadata:
        """Save or update user metadata in the database.

        Returns:
            UserMetadata instance refreshed from database
        """
        now = datetime.now(UTC)

        # Encrypt metadata
        encrypted_content = self.encrypt_metadata()

        async with async_database() as db_conn:
            stmt = pg_insert(UserMetadataTable).values(
                object_key=self.object_key,
                user_id=self.user_id,
                content=encrypted_content,
                created_at=self.created_at,
                updated_at=now,
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=["object_key"],
                set_={
                    "content": stmt.excluded.content,
                    "updated_at": stmt.excluded.updated_at,
                },
            ).returning(UserMetadataTable)

            result = await db_conn.execute(stmt)
            row = result.scalar_one()

            # Return with decrypted fields
            metadata_dict = UserMetadata.decrypt_metadata(row.content) if row.content else {}

            return UserMetadata(
                id=row.id,
                user_id=row.user_id,
                preferred_name=metadata_dict.get("preferred_name"),
                country=metadata_dict.get("country", "rather_not_say"),
                timezone=metadata_dict.get("timezone", "rather_not_say"),
                response_speed=metadata_dict.get("response_speed", "normal"),
                response_speed_adj=metadata_dict.get("response_speed_adj", 0),
                communication_style=metadata_dict.get("communication_style"),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    @classmethod
    @db_retry()
    async def get_by_user_id(
        cls,
        *,
        user_id: int,
    ) -> UserMetadata | None:
        """Retrieve user metadata by user ID with decrypted fields.

        Args:
            user_id: Internal user ID (FK to users.id)

        Returns:
            UserMetadata instance if found, None otherwise
        """
        async with async_database() as db_conn:
            stmt = select(UserMetadataTable).where(UserMetadataTable.user_id == user_id)
            result = await db_conn.execute(stmt)
            row = result.scalars().first()

            if row is None:
                return None

            # Decrypt metadata fields
            metadata_dict = cls.decrypt_metadata(row.content) if row.content else {}

            return cls(
                id=row.id,
                user_id=row.user_id,
                preferred_name=metadata_dict.get("preferred_name"),
                country=metadata_dict.get("country", "rather_not_say"),
                timezone=metadata_dict.get("timezone", "rather_not_say"),
                response_speed=metadata_dict.get("response_speed", "normal"),
                response_speed_adj=metadata_dict.get("response_speed_adj", 0),
                communication_style=metadata_dict.get("communication_style"),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
