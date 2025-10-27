"""Tests for JobState model."""

from datetime import UTC, datetime

import pytest

from areyouok_telegram.data.models import JobState


def test_job_state_object_key():
    """Test JobState.object_key generation is consistent."""
    js1 = JobState(job_name="test_job", state_data={"a": 1})
    js2 = JobState(job_name="test_job", state_data={"b": 2})
    assert js1.object_key == js2.object_key
    assert len(js1.object_key) == 64  # SHA-256 hex digest


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_job_state_save_and_get(mock_db_session):
    """Test JobState.save() upserts and get() retrieves."""
    js = JobState(job_name="ping_job", state_data={"last_run": "2025-01-01"})

    class Row:
        id = 3
        job_name = "ping_job"
        state_data = {"last_run": "2025-01-01"}
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)

    class _ResOne:
        def scalar_one(self):
            return Row()

    mock_db_session.execute.return_value = _ResOne()
    saved = await js.save()
    assert saved.id == 3
    assert saved.state_data == {"last_run": "2025-01-01"}

    # Mock get()
    class _ResOneOrNone:
        def scalar_one_or_none(self):
            return Row()

    mock_db_session.execute.return_value = _ResOneOrNone()
    fetched = await JobState.get(job_name="ping_job")
    assert fetched and fetched.job_name == "ping_job"


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_job_state_delete(mock_db_session):
    """Test JobState.delete() removes the record."""
    js = JobState(job_name="temp_job", state_data={})

    await js.delete()
    # Verify that execute was called to run the DELETE statement
    mock_db_session.execute.assert_called_once()
