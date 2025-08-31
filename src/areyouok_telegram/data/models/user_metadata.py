import hashlib
from datetime import UTC
from datetime import datetime
from typing import Any
from typing import Optional

from cachetools import TTLCache
from sqlalchemy import BOOLEAN
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


class InvalidFieldTypeError(Exception):
    """Raised when an invalid type is provided for a field."""

    def __init__(self, field: str, expected_type: str):
        super().__init__(f"Field '{field}' must be {expected_type}")
        self.field = field
        self.expected_type = expected_type


class UserMetadata(Base):
    """User metadata and preferences with selective field encryption."""

    __tablename__ = "user_metadata"
    __table_args__ = {"schema": ENV}

    # Field mappings for validation
    _ENCRYPTED_FIELDS = {
        "preferred_name": "_preferred_name",
        "country": "_country",
        "timezone": "_timezone",
        "communication_style": "_communication_style",
    }

    _UNENCRYPTED_FIELDS = {
        "daily_checkin": "daily_checkin",
    }

    # TTL cache for decrypted fields (1 hour TTL, max 1000 entries)
    _field_cache: TTLCache[str, str] = TTLCache(maxsize=1000, ttl=1 * 60 * 60)

    user_key = Column(String, nullable=False, unique=True)
    user_id = Column(String, nullable=False, unique=True)

    # Encrypted Fields (stored as _field_name in database)
    _preferred_name = Column(String, nullable=True)
    _country = Column(String, nullable=True)
    _timezone = Column(String, nullable=True)
    _communication_style = Column(String, nullable=True)

    # Unencrypted Feature Flags
    daily_checkin = Column(BOOLEAN, nullable=False, default=False)

    # Metadata
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    @staticmethod
    def generate_user_key(user_id: str) -> str:
        """Generate a unique key for user metadata based on their user ID."""
        return hashlib.sha256(f"metadata:{user_id}".encode()).hexdigest()

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

    # Read-only properties for encrypted fields
    @property
    def preferred_name(self) -> str | None:
        """Get user's preferred name."""
        return self._decrypt_field("preferred_name", self._preferred_name)

    @property
    def country(self) -> str | None:
        """Get user's country."""
        return self._decrypt_field("country", self._country)

    @property
    def timezone(self) -> str | None:
        """Get user's timezone."""
        return self._decrypt_field("timezone", self._timezone)

    @property
    def communication_style(self) -> str | None:
        """Get user's communication style."""
        return self._decrypt_field("communication_style", self._communication_style)

    @classmethod
    @traced(extract_args=["user_id", "field"])
    async def update_metadata(cls, db_conn: AsyncSession, *, user_id: str, field: str, value: Any) -> "UserMetadata":
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
            InvalidFieldTypeError: If value type is incorrect for the field
        """
        # Validate field name
        if field not in cls._ENCRYPTED_FIELDS and field not in cls._UNENCRYPTED_FIELDS:
            valid_fields = list(cls._ENCRYPTED_FIELDS.keys()) + list(cls._UNENCRYPTED_FIELDS.keys())
            raise InvalidFieldError(field, valid_fields)

        # Type checking
        if field in cls._ENCRYPTED_FIELDS:
            if value is not None and not isinstance(value, str):
                raise InvalidFieldTypeError(field, "a string or None")
        elif field == "daily_checkin":
            if not isinstance(value, bool):
                raise InvalidFieldTypeError(field, "a boolean")

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

        # Return the updated user metadata
        return await cls.get_by_user_id(db_conn, user_id)

    @classmethod
    async def get_by_user_id(
        cls,
        db_conn: AsyncSession,
        *,
        user_id: str,
    ) -> Optional["UserMetadata"]:
        """Retrieve user metadata by user ID."""
        stmt = select(cls).where(cls.user_id == user_id)
        result = await db_conn.execute(stmt)
        return result.scalars().first()
