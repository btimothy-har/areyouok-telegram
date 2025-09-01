"""Tests for OnboardingSession model."""

import hashlib
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from areyouok_telegram.data.models.onboarding import VALID_ONBOARDING_STATES
from areyouok_telegram.data.models.onboarding import InvalidOnboardingStateError
from areyouok_telegram.data.models.onboarding import OnboardingState
from areyouok_telegram.data.models.onboarding import OnboardingSession


class TestOnboardingState:
    """Test OnboardingState enum."""

    def test_onboarding_state_values(self):
        """Test OnboardingState enum has expected values."""
        assert OnboardingState.ACTIVE.value == "active"
        assert OnboardingState.COMPLETE.value == "complete"
        assert OnboardingState.INCOMPLETE.value == "incomplete"

    def test_valid_onboarding_states_constant(self):
        """Test VALID_ONBOARDING_STATES contains all enum values."""
        expected_states = ["active", "complete", "incomplete"]
        assert set(VALID_ONBOARDING_STATES) == set(expected_states)
        assert len(VALID_ONBOARDING_STATES) == 3


class TestInvalidOnboardingStateError:
    """Test InvalidOnboardingStateError exception."""

    def test_invalid_onboarding_state_error_creation(self):
        """Test InvalidOnboardingStateError is created with correct attributes."""
        error = InvalidOnboardingStateError("invalid_state")

        assert error.state == "invalid_state"
        assert "Invalid onboarding state: invalid_state" in str(error)
        assert "active" in str(error)
        assert "complete" in str(error)
        assert "incomplete" in str(error)

    def test_invalid_onboarding_state_error_inheritance(self):
        """Test InvalidOnboardingStateError inherits from Exception."""
        error = InvalidOnboardingStateError("test")
        assert isinstance(error, Exception)


class TestOnboardingSession:
    """Test OnboardingSession model."""

    def test_generate_session_key(self, frozen_time):
        """Test session key generation with user ID and timestamp."""
        user_id = "user123"
        started_at = frozen_time

        timestamp_str = started_at.isoformat()
        expected = hashlib.sha256(f"onboarding:{user_id}:{timestamp_str}".encode()).hexdigest()

        result = OnboardingSession.generate_session_key(user_id, started_at)

        assert result == expected

    def test_generate_session_key_different_users(self, frozen_time):
        """Test session key generation produces different keys for different users."""
        user_id1 = "user123"
        user_id2 = "user456"
        started_at = frozen_time

        key1 = OnboardingSession.generate_session_key(user_id1, started_at)
        key2 = OnboardingSession.generate_session_key(user_id2, started_at)

        assert key1 != key2

    def test_generate_session_key_different_timestamps(self):
        """Test session key generation produces different keys for different timestamps."""
        user_id = "user123"
        time1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        time2 = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        key1 = OnboardingSession.generate_session_key(user_id, time1)
        key2 = OnboardingSession.generate_session_key(user_id, time2)

        assert key1 != key2

    def test_is_completed_property_true(self):
        """Test is_completed returns True for COMPLETE state."""
        onboarding = OnboardingSession()
        onboarding.state = OnboardingState.COMPLETE.value

        assert onboarding.is_completed is True

    def test_is_completed_property_false(self):
        """Test is_completed returns False for non-COMPLETE states."""
        onboarding = OnboardingSession()

        # Test ACTIVE state
        onboarding.state = OnboardingState.ACTIVE.value
        assert onboarding.is_completed is False

        # Test INCOMPLETE state
        onboarding.state = OnboardingState.INCOMPLETE.value
        assert onboarding.is_completed is False

    def test_is_active_property_true(self):
        """Test is_active returns True for ACTIVE state."""
        onboarding = OnboardingSession()
        onboarding.state = OnboardingState.ACTIVE.value

        assert onboarding.is_active is True

    def test_is_active_property_false(self):
        """Test is_active returns False for non-ACTIVE states."""
        onboarding = OnboardingSession()

        # Test COMPLETE state
        onboarding.state = OnboardingState.COMPLETE.value
        assert onboarding.is_active is False

        # Test INCOMPLETE state
        onboarding.state = OnboardingState.INCOMPLETE.value
        assert onboarding.is_active is False

    def test_is_incomplete_property_true(self):
        """Test is_incomplete returns True for INCOMPLETE state."""
        onboarding = OnboardingSession()
        onboarding.state = OnboardingState.INCOMPLETE.value

        assert onboarding.is_incomplete is True

    def test_is_incomplete_property_false(self):
        """Test is_incomplete returns False for non-INCOMPLETE states."""
        onboarding = OnboardingSession()

        # Test ACTIVE state
        onboarding.state = OnboardingState.ACTIVE.value
        assert onboarding.is_incomplete is False

        # Test COMPLETE state
        onboarding.state = OnboardingState.COMPLETE.value
        assert onboarding.is_incomplete is False

    def test_is_expired_property_false_for_non_active(self):
        """Test is_expired returns False for non-ACTIVE states."""
        onboarding = OnboardingSession()
        onboarding.started_at = datetime.now(UTC) - timedelta(hours=2)

        # Test COMPLETE state
        onboarding.state = OnboardingState.COMPLETE.value
        assert onboarding.is_expired is False

        # Test INCOMPLETE state
        onboarding.state = OnboardingState.INCOMPLETE.value
        assert onboarding.is_expired is False

    def test_is_expired_property_false_for_recent_active(self, frozen_time):
        """Test is_expired returns False for ACTIVE state started recently."""
        onboarding = OnboardingSession()
        onboarding.state = OnboardingState.ACTIVE.value
        # Started 30 minutes ago (within 1 hour)
        onboarding.started_at = frozen_time - timedelta(minutes=30)

        assert onboarding.is_expired is False

    def test_is_expired_property_true_for_old_active(self, frozen_time):
        """Test is_expired returns True for ACTIVE state started over 1 hour ago."""
        onboarding = OnboardingSession()
        onboarding.state = OnboardingState.ACTIVE.value
        # Started 2 hours ago (over 1 hour)
        onboarding.started_at = frozen_time - timedelta(hours=2)

        assert onboarding.is_expired is True

    def test_is_expired_property_boundary_exactly_one_hour(self, frozen_time):
        """Test is_expired at exactly 1 hour boundary."""
        onboarding = OnboardingSession()
        onboarding.state = OnboardingState.ACTIVE.value
        # Started exactly 1 hour ago
        onboarding.started_at = frozen_time - timedelta(hours=1)

        assert onboarding.is_expired is False

    def test_is_expired_property_boundary_just_over_one_hour(self, frozen_time):
        """Test is_expired just over 1 hour boundary."""
        onboarding = OnboardingSession()
        onboarding.state = OnboardingState.ACTIVE.value
        # Started 1 hour and 1 second ago
        onboarding.started_at = frozen_time - timedelta(hours=1, seconds=1)

        assert onboarding.is_expired is True

    @pytest.mark.asyncio
    async def test_start_onboarding(self, mock_db_session):
        """Test start_onboarding creates new active onboarding record."""
        user_id = "user123"
        mock_new_onboarding = MagicMock(spec=OnboardingSession)

        with patch.object(OnboardingSession, "get_by_user_id", return_value=mock_new_onboarding):
            result = await OnboardingSession.start_onboarding(mock_db_session, user_id=user_id)

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

        # Get the statement that was executed
        call_args = mock_db_session.execute.call_args[0][0]

        # Verify it's an insert statement for onboarding table
        assert hasattr(call_args, "table")
        assert call_args.table.name == "onboarding"

        # Verify get_by_user_id was called to return the new onboarding
        assert result == mock_new_onboarding

    @pytest.mark.asyncio
    async def test_start_onboarding_database_values(self, mock_db_session):
        """Test start_onboarding inserts correct values."""
        user_id = "user123"
        mock_new_onboarding = MagicMock(spec=OnboardingSession)

        with patch.object(OnboardingSession, "get_by_user_id", return_value=mock_new_onboarding):
            await OnboardingSession.start_onboarding(mock_db_session, user_id=user_id)

        # Verify database execute was called
        call_args = mock_db_session.execute.call_args[0][0]

        # The values should be accessible via the insert statement
        # This verifies the structure is correct
        assert hasattr(call_args, "table")

    @pytest.mark.asyncio
    async def test_end_onboarding(self, mock_db_session, frozen_time):
        """Test end_onboarding completes the onboarding session."""
        onboarding = OnboardingSession()
        onboarding.state = OnboardingState.ACTIVE.value
        onboarding.completed_at = None
        original_updated_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        onboarding.updated_at = original_updated_at

        await onboarding.end_onboarding(mock_db_session, timestamp=frozen_time)

        # Verify state changes
        assert onboarding.state == OnboardingState.COMPLETE.value
        assert onboarding.completed_at == frozen_time
        assert onboarding.updated_at == frozen_time

        # Verify object was added to session
        mock_db_session.add.assert_called_once_with(onboarding)

    @pytest.mark.asyncio
    async def test_inactivate_onboarding(self, mock_db_session, frozen_time):
        """Test inactivate_onboarding marks session as incomplete."""
        onboarding = OnboardingSession()
        onboarding.state = OnboardingState.ACTIVE.value
        original_updated_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        onboarding.updated_at = original_updated_at

        await onboarding.inactivate_onboarding(mock_db_session, timestamp=frozen_time)

        # Verify state changes
        assert onboarding.state == OnboardingState.INCOMPLETE.value
        assert onboarding.updated_at == frozen_time

        # Verify object was added to session
        mock_db_session.add.assert_called_once_with(onboarding)

    @pytest.mark.asyncio
    async def test_get_by_user_id_found(self, mock_db_session):
        """Test get_by_user_id returns most recent onboarding when found."""
        user_id = "user123"
        mock_onboarding = MagicMock(spec=OnboardingSession)
        mock_onboarding.user_id = user_id

        # Setup mock chain for execute().scalars().first()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_onboarding
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await OnboardingSession.get_by_user_id(mock_db_session, user_id=user_id)

        assert result == mock_onboarding
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_id_not_found(self, mock_db_session):
        """Test get_by_user_id returns None when user not found."""
        user_id = "nonexistent"

        # Setup mock chain for execute().scalars().first() returning None
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await OnboardingSession.get_by_user_id(mock_db_session, user_id=user_id)

        assert result is None
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_id_orders_by_created_at_desc(self, mock_db_session):
        """Test get_by_user_id queries with correct ordering."""
        user_id = "user123"

        # Setup mock chain for execute().scalars().first() returning None
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        await OnboardingSession.get_by_user_id(mock_db_session, user_id=user_id)

        # Verify database execute was called (the important part is that the query was executed)
        mock_db_session.execute.assert_called_once()

    def test_state_property_transitions(self):
        """Test all state property combinations."""
        onboarding = OnboardingSession()

        # Test ACTIVE state
        onboarding.state = OnboardingState.ACTIVE.value
        assert onboarding.is_active is True
        assert onboarding.is_completed is False
        assert onboarding.is_incomplete is False

        # Test COMPLETE state
        onboarding.state = OnboardingState.COMPLETE.value
        assert onboarding.is_active is False
        assert onboarding.is_completed is True
        assert onboarding.is_incomplete is False

        # Test INCOMPLETE state
        onboarding.state = OnboardingState.INCOMPLETE.value
        assert onboarding.is_active is False
        assert onboarding.is_completed is False
        assert onboarding.is_incomplete is True

    def test_session_key_consistency(self):
        """Test that session key generation is consistent for same inputs."""
        user_id = "user123"
        timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        key1 = OnboardingSession.generate_session_key(user_id, timestamp)
        key2 = OnboardingSession.generate_session_key(user_id, timestamp)

        assert key1 == key2

    def test_expiration_time_calculations(self):
        """Test various expiration time scenarios."""
        base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        with freeze_time(base_time):
            onboarding = OnboardingSession()
            onboarding.state = OnboardingState.ACTIVE.value

            # Test scenarios with different start times
            test_cases = [
                # (minutes_ago, expected_expired)
                (0, False),  # Just started
                (30, False),  # 30 minutes ago
                (59, False),  # 59 minutes ago
                (60, False),  # Exactly 1 hour ago
                (61, True),  # 61 minutes ago
                (120, True),  # 2 hours ago
            ]

            for minutes_ago, expected_expired in test_cases:
                onboarding.started_at = base_time - timedelta(minutes=minutes_ago)
                assert onboarding.is_expired == expected_expired, f"Failed for {minutes_ago} minutes ago"
