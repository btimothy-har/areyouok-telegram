"""Tests for JobState model."""

from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from areyouok_telegram.data import JobState


class TestJobState:
    """Test JobState model."""

    @pytest.mark.asyncio
    async def test_save_state(self, mock_db_session):
        """Test saving job state."""
        job_name = "test_job"
        state_data = {
            "last_run_time": datetime.now(UTC).isoformat(),
            "processed_count": 100,
        }

        # Mock the database execute call
        mock_result = MagicMock()
        mock_job_state = MagicMock(spec=JobState)
        mock_job_state.job_name = job_name
        mock_job_state.state_data = state_data
        mock_result.scalar_one = MagicMock(return_value=mock_job_state)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Save state
        job_state = await JobState.save_state(mock_db_session, job_name=job_name, state_data=state_data)

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify the returned object
        assert job_state.job_name == job_name
        assert job_state.state_data == state_data

    @pytest.mark.asyncio
    async def test_get_state(self, mock_db_session):
        """Test retrieving job state."""
        job_name = "test_job"
        state_data = {"last_run_time": datetime.now(UTC).isoformat()}

        # Mock the database execute call
        mock_result = MagicMock()
        mock_job_state = MagicMock(spec=JobState)
        mock_job_state.state_data = state_data
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_job_state)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Get state
        retrieved_state = await JobState.get_state(mock_db_session, job_name=job_name)

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify the returned data
        assert retrieved_state == state_data

    @pytest.mark.asyncio
    async def test_get_state_nonexistent(self, mock_db_session):
        """Test getting state for a job that doesn't exist."""
        # Mock the database execute call to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        state = await JobState.get_state(mock_db_session, job_name="nonexistent_job")

        # Verify execute was called
        mock_db_session.execute.assert_called_once()

        # Verify None is returned
        assert state is None

    def test_generate_job_key(self):
        """Test job key generation is consistent."""
        job_name = "test_job"

        key1 = JobState.generate_job_key(job_name)
        key2 = JobState.generate_job_key(job_name)

        assert key1 == key2
        assert isinstance(key1, str)
        assert len(key1) == 64  # SHA-256 hex digest length

    def test_different_jobs_have_different_keys(self):
        """Test that different job names produce different keys."""
        key1 = JobState.generate_job_key("job1")
        key2 = JobState.generate_job_key("job2")

        assert key1 != key2

    @pytest.mark.asyncio
    async def test_save_state_upserts_new_record(self, mock_db_session):
        """Test that save_state creates a new record when it doesn't exist (upsert insert case)."""
        job_name = "new_job"
        state_data = {"field1": "value1", "field2": "value2"}

        # Mock the database execute call for INSERT
        mock_result = MagicMock()
        mock_job_state = MagicMock(spec=JobState)
        mock_job_state.job_name = job_name
        mock_job_state.state_data = state_data
        mock_result.scalar_one = MagicMock(return_value=mock_job_state)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Save state (will insert since it doesn't exist)
        job_state = await JobState.save_state(mock_db_session, job_name=job_name, state_data=state_data)

        # Verify execute was called once (upsert statement)
        mock_db_session.execute.assert_called_once()

        # Verify the returned object
        assert job_state.job_name == job_name
        assert job_state.state_data == state_data

    @pytest.mark.asyncio
    async def test_save_state_upserts_existing_record(self, mock_db_session):
        """Test that save_state updates an existing record (upsert update case)."""
        job_name = "existing_job"
        new_state_data = {"last_run_time": "2025-01-02T00:00:00", "count": 200, "new_field": "new_value"}

        # Mock the database execute call for UPDATE (on conflict)
        mock_result = MagicMock()
        mock_job_state = MagicMock(spec=JobState)
        mock_job_state.job_name = job_name
        mock_job_state.state_data = new_state_data
        mock_result.scalar_one = MagicMock(return_value=mock_job_state)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Save state (will update since it exists)
        job_state = await JobState.save_state(mock_db_session, job_name=job_name, state_data=new_state_data)

        # Verify execute was called once (upsert statement handles both insert and update)
        mock_db_session.execute.assert_called_once()

        # Verify the returned object has the new state
        assert job_state.job_name == job_name
        assert job_state.state_data == new_state_data

    @pytest.mark.asyncio
    async def test_delete_state_removes_existing(self, mock_db_session):
        """Test that delete_state removes an existing job state (lines 149-156)."""
        job_name = "test_job"

        # Mock the select query to return a job state
        mock_job_state = MagicMock(spec=JobState)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_job_state)
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.delete = AsyncMock()

        # Delete state
        await JobState.delete_state(mock_db_session, job_name=job_name)

        # Verify execute was called to select the state
        mock_db_session.execute.assert_called_once()

        # Verify delete was called on the job state
        mock_db_session.delete.assert_called_once_with(mock_job_state)

    @pytest.mark.asyncio
    async def test_delete_state_does_nothing_when_not_found(self, mock_db_session):
        """Test that delete_state does nothing when job state doesn't exist (line 155-156)."""
        job_name = "nonexistent_job"

        # Mock the select query to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.delete = AsyncMock()

        # Delete state
        await JobState.delete_state(mock_db_session, job_name=job_name)

        # Verify execute was called to select the state
        mock_db_session.execute.assert_called_once()

        # Verify delete was NOT called since state doesn't exist
        mock_db_session.delete.assert_not_called()
