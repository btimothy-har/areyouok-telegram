"""Tests for UserMetadata model."""

from datetime import UTC, datetime

import pytest

from areyouok_telegram.data.models import InvalidCountryCodeError, InvalidTimezoneError, UserMetadata


def test_user_metadata_field_validators():
    """Test UserMetadata field validators for country, timezone, response_speed."""
    # Valid country code
    um = UserMetadata(user_id=1, country="USA")
    assert um.country == "USA"

    # Invalid country code
    with pytest.raises(InvalidCountryCodeError):
        UserMetadata(user_id=1, country="XYZ")

    # Valid timezone
    um2 = UserMetadata(user_id=2, timezone="America/New_York")
    assert um2.timezone == "America/New_York"

    # Invalid timezone
    with pytest.raises(InvalidTimezoneError):
        UserMetadata(user_id=2, timezone="Invalid/Zone")


def test_user_metadata_response_wait_time():
    """Test UserMetadata.response_wait_time calculation."""
    um_fast = UserMetadata(user_id=1, response_speed="fast")
    assert um_fast.response_wait_time == 0.0

    um_normal = UserMetadata(user_id=2, response_speed="normal", response_speed_adj=1)
    assert um_normal.response_wait_time == 3.0

    um_slow = UserMetadata(user_id=3, response_speed="slow", response_speed_adj=-2)
    assert um_slow.response_wait_time == 3.0


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_user_metadata_save_and_get_by_user_id(mock_db_session):
    """Test UserMetadata.save() encrypts and get_by_user_id() decrypts."""
    um = UserMetadata(
        user_id=100,
        preferred_name="Alice",
        country="USA",
        timezone="America/Los_Angeles",
        response_speed="normal",
    )

    # Mock save returning encrypted row
    encrypted_content = um.encrypt_metadata()

    class Row:
        id = 5
        user_id = 100
        content = encrypted_content
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)

    class _ResOne:
        def scalar_one(self):
            return Row()

    mock_db_session.execute.return_value = _ResOne()
    saved = await um.save()
    assert saved.id == 5
    assert saved.preferred_name == "Alice"

    # Mock get_by_user_id
    class _ScalarsFirst:
        def scalars(self):
            class _S:
                def first(self):
                    return Row()

            return _S()

    mock_db_session.execute.return_value = _ScalarsFirst()
    fetched = await UserMetadata.get_by_user_id(user_id=100)
    assert fetched and fetched.preferred_name == "Alice"


def test_user_metadata_to_dict():
    """Test UserMetadata.to_dict() serialization."""
    um = UserMetadata(user_id=7, preferred_name="Bob", response_speed="fast")
    d = um.to_dict()
    assert d["user_id"] == 7
    assert d["preferred_name"] == "Bob"
    assert d["response_speed"] == "fast"

