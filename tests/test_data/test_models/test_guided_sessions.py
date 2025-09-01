"""Tests for GuidedSessions model."""

import hashlib
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from areyouok_telegram.data.models.guided_sessions import VALID_GUIDED_SESSION_STATES
from areyouok_telegram.data.models.guided_sessions import VALID_GUIDED_SESSION_TYPES
from areyouok_telegram.data.models.guided_sessions import VALID_ONBOARDING_STATES
from areyouok_telegram.data.models.guided_sessions import GuidedSessions
from areyouok_telegram.data.models.guided_sessions import GuidedSessionState
from areyouok_telegram.data.models.guided_sessions import GuidedSessionType
from areyouok_telegram.data.models.guided_sessions import InvalidGuidedSessionStateError
from areyouok_telegram.data.models.guided_sessions import InvalidGuidedSessionTypeError

# Import backward compatibility aliases for testing
from areyouok_telegram.data.models.guided_sessions import InvalidOnboardingStateError
from areyouok_telegram.data.models.guided_sessions import OnboardingSession
from areyouok_telegram.data.models.guided_sessions import OnboardingState


class TestGuidedSessionType:
    """Test GuidedSessionType enum."""

    def test_guided_session_type_values(self):
        """Test GuidedSessionType enum has expected values."""
        assert GuidedSessionType.ONBOARDING.value == "onboarding"

    def test_valid_guided_session_types_constant(self):
        """Test VALID_GUIDED_SESSION_TYPES contains all enum values."""
        expected_types = ["onboarding"]
        assert set(VALID_GUIDED_SESSION_TYPES) == set(expected_types)
        assert len(VALID_GUIDED_SESSION_TYPES) == 1


class TestGuidedSessionState:
    """Test GuidedSessionState enum."""

    def test_guided_session_state_values(self):
        """Test GuidedSessionState enum has expected values."""
        assert GuidedSessionState.ACTIVE.value == "active"
        assert GuidedSessionState.COMPLETE.value == "complete"
        assert GuidedSessionState.INCOMPLETE.value == "incomplete"

    def test_valid_guided_session_states_constant(self):
        """Test VALID_GUIDED_SESSION_STATES contains all enum values."""
        expected_states = ["active", "complete", "incomplete"]
        assert set(VALID_GUIDED_SESSION_STATES) == set(expected_states)
        assert len(VALID_GUIDED_SESSION_STATES) == 3


class TestInvalidGuidedSessionStateError:
    """Test InvalidGuidedSessionStateError exception."""

    def test_invalid_guided_session_state_error_creation(self):
        """Test InvalidGuidedSessionStateError is created with correct attributes."""
        error = InvalidGuidedSessionStateError("invalid_state")

        assert error.state == "invalid_state"
        assert "Invalid guided session state: invalid_state" in str(error)
        assert "active" in str(error)
        assert "complete" in str(error)
        assert "incomplete" in str(error)

    def test_invalid_guided_session_state_error_inheritance(self):
        """Test InvalidGuidedSessionStateError inherits from Exception."""
        error = InvalidGuidedSessionStateError("test")
        assert isinstance(error, Exception)


class TestInvalidGuidedSessionTypeError:
    """Test InvalidGuidedSessionTypeError exception."""

    def test_invalid_guided_session_type_error_creation(self):
        """Test InvalidGuidedSessionTypeError is created with correct attributes."""
        error = InvalidGuidedSessionTypeError("invalid_type")

        assert error.session_type == "invalid_type"
        assert "Invalid guided session type: invalid_type" in str(error)
        assert "onboarding" in str(error)

    def test_invalid_guided_session_type_error_inheritance(self):
        """Test InvalidGuidedSessionTypeError inherits from Exception."""
        error = InvalidGuidedSessionTypeError("test")
        assert isinstance(error, Exception)


class TestGuidedSessions:
    """Test GuidedSessions model."""

    def test_generate_guided_session_key(self, frozen_time):
        """Test guided session key generation with user ID, session type, and timestamp."""
        user_id = "user123"
        session_type = "onboarding"
        started_at = frozen_time

        timestamp_str = started_at.isoformat()
        expected = hashlib.sha256(f"{session_type}:{user_id}:{timestamp_str}".encode()).hexdigest()

        result = GuidedSessions.generate_guided_session_key(user_id, session_type, started_at)

        assert result == expected

    def test_generate_guided_session_key_different_users(self, frozen_time):
        """Test guided session key generation produces different keys for different users."""
        user_id1 = "user123"
        user_id2 = "user456"
        session_type = "onboarding"
        started_at = frozen_time

        key1 = GuidedSessions.generate_guided_session_key(user_id1, session_type, started_at)
        key2 = GuidedSessions.generate_guided_session_key(user_id2, session_type, started_at)

        assert key1 != key2

    def test_generate_guided_session_key_different_types(self, frozen_time):
        """Test guided session key generation produces different keys for different session types."""
        user_id = "user123"
        session_type1 = "onboarding"
        session_type2 = "mindfulness"
        started_at = frozen_time

        key1 = GuidedSessions.generate_guided_session_key(user_id, session_type1, started_at)
        key2 = GuidedSessions.generate_guided_session_key(user_id, session_type2, started_at)

        assert key1 != key2

    def test_generate_guided_session_key_different_timestamps(self):
        """Test guided session key generation produces different keys for different timestamps."""
        user_id = "user123"
        session_type = "onboarding"
        time1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        time2 = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        key1 = GuidedSessions.generate_guided_session_key(user_id, session_type, time1)
        key2 = GuidedSessions.generate_guided_session_key(user_id, session_type, time2)

        assert key1 != key2

    def test_is_completed_property_true(self):
        """Test is_completed returns True for COMPLETE state."""
        guided_session = GuidedSessions()
        guided_session.state = GuidedSessionState.COMPLETE.value

        assert guided_session.is_completed is True

    def test_is_completed_property_false(self):
        """Test is_completed returns False for non-COMPLETE states."""
        guided_session = GuidedSessions()

        # Test ACTIVE state
        guided_session.state = GuidedSessionState.ACTIVE.value
        assert guided_session.is_completed is False

        # Test INCOMPLETE state
        guided_session.state = GuidedSessionState.INCOMPLETE.value
        assert guided_session.is_completed is False

    def test_is_active_property_true(self):
        """Test is_active returns True for ACTIVE state."""
        guided_session = GuidedSessions()
        guided_session.state = GuidedSessionState.ACTIVE.value

        assert guided_session.is_active is True

    def test_is_active_property_false(self):
        """Test is_active returns False for non-ACTIVE states."""
        guided_session = GuidedSessions()

        # Test COMPLETE state
        guided_session.state = GuidedSessionState.COMPLETE.value
        assert guided_session.is_active is False

        # Test INCOMPLETE state
        guided_session.state = GuidedSessionState.INCOMPLETE.value
        assert guided_session.is_active is False

    def test_is_incomplete_property_true(self):
        """Test is_incomplete returns True for INCOMPLETE state."""
        guided_session = GuidedSessions()
        guided_session.state = GuidedSessionState.INCOMPLETE.value

        assert guided_session.is_incomplete is True

    def test_is_incomplete_property_false(self):
        """Test is_incomplete returns False for non-INCOMPLETE states."""
        guided_session = GuidedSessions()

        # Test ACTIVE state
        guided_session.state = GuidedSessionState.ACTIVE.value
        assert guided_session.is_incomplete is False

        # Test COMPLETE state
        guided_session.state = GuidedSessionState.COMPLETE.value
        assert guided_session.is_incomplete is False

    def test_is_expired_property_false_for_non_active(self):
        """Test is_expired returns False for non-ACTIVE states."""
        guided_session = GuidedSessions()
        guided_session.started_at = datetime.now(UTC) - timedelta(hours=2)

        # Test COMPLETE state
        guided_session.state = GuidedSessionState.COMPLETE.value
        assert guided_session.is_expired is False

        # Test INCOMPLETE state
        guided_session.state = GuidedSessionState.INCOMPLETE.value
        assert guided_session.is_expired is False

    def test_is_expired_property_false_for_recent_active(self, frozen_time):
        """Test is_expired returns False for ACTIVE state started recently."""
        guided_session = GuidedSessions()
        guided_session.state = GuidedSessionState.ACTIVE.value
        # Started 30 minutes ago (within 1 hour)
        guided_session.started_at = frozen_time - timedelta(minutes=30)

        assert guided_session.is_expired is False

    def test_is_expired_property_true_for_old_active(self, frozen_time):
        """Test is_expired returns True for ACTIVE state started over 1 hour ago."""
        guided_session = GuidedSessions()
        guided_session.state = GuidedSessionState.ACTIVE.value
        # Started 2 hours ago (over 1 hour)
        guided_session.started_at = frozen_time - timedelta(hours=2)

        assert guided_session.is_expired is True

    @pytest.mark.asyncio
    async def test_start_guided_session(self, mock_db_session):
        """Test start_guided_session creates new active guided session record."""
        user_id = "user123"
        session_key = "session123"
        session_type = GuidedSessionType.ONBOARDING.value
        mock_new_session = MagicMock(spec=GuidedSessions)

        with patch.object(GuidedSessions, "get_by_user_id_and_type", return_value=mock_new_session):
            result = await GuidedSessions.start_guided_session(
                mock_db_session, user_id=user_id, session_key=session_key, session_type=session_type
            )

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

        # Get the statement that was executed
        call_args = mock_db_session.execute.call_args[0][0]

        # Verify it's an insert statement for guided_sessions table
        assert hasattr(call_args, "table")
        assert call_args.table.name == "guided_sessions"

        # Verify get_by_user_id_and_type was called to return the new session
        assert result == mock_new_session

    @pytest.mark.asyncio
    async def test_start_guided_session_invalid_type(self, mock_db_session):
        """Test start_guided_session raises error for invalid session type."""
        user_id = "user123"
        session_key = "session123"
        session_type = "invalid_type"

        with pytest.raises(InvalidGuidedSessionTypeError) as exc_info:
            await GuidedSessions.start_guided_session(
                mock_db_session, user_id=user_id, session_key=session_key, session_type=session_type
            )

        assert exc_info.value.session_type == "invalid_type"

    @pytest.mark.asyncio
    async def test_end_guided_session(self, mock_db_session, frozen_time):
        """Test end_guided_session completes the guided session."""
        guided_session = GuidedSessions()
        guided_session.state = GuidedSessionState.ACTIVE.value
        guided_session.completed_at = None
        original_updated_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        guided_session.updated_at = original_updated_at

        await guided_session.end_guided_session(mock_db_session, timestamp=frozen_time)

        # Verify state changes
        assert guided_session.state == GuidedSessionState.COMPLETE.value
        assert guided_session.completed_at == frozen_time
        assert guided_session.updated_at == frozen_time

        # Verify object was added to session
        mock_db_session.add.assert_called_once_with(guided_session)

    @pytest.mark.asyncio
    async def test_inactivate_guided_session(self, mock_db_session, frozen_time):
        """Test inactivate_guided_session marks session as incomplete."""
        guided_session = GuidedSessions()
        guided_session.state = GuidedSessionState.ACTIVE.value
        original_updated_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        guided_session.updated_at = original_updated_at

        await guided_session.inactivate_guided_session(mock_db_session, timestamp=frozen_time)

        # Verify state changes
        assert guided_session.state == GuidedSessionState.INCOMPLETE.value
        assert guided_session.updated_at == frozen_time

        # Verify object was added to session
        mock_db_session.add.assert_called_once_with(guided_session)

    @pytest.mark.asyncio
    async def test_get_by_user_id_and_type_found(self, mock_db_session):
        """Test get_by_user_id_and_type returns most recent session when found."""
        user_id = "user123"
        session_type = GuidedSessionType.ONBOARDING.value
        mock_session = MagicMock(spec=GuidedSessions)
        mock_session.user_id = user_id
        mock_session.session_type = session_type

        # Setup mock chain for execute().scalars().first()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_session
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await GuidedSessions.get_by_user_id_and_type(
            mock_db_session, user_id=user_id, session_type=session_type
        )

        assert result == mock_session
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_id_found(self, mock_db_session):
        """Test get_by_user_id returns most recent session when found."""
        user_id = "user123"
        mock_session = MagicMock(spec=GuidedSessions)
        mock_session.user_id = user_id

        # Setup mock chain for execute().scalars().first()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_session
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await GuidedSessions.get_by_user_id(mock_db_session, user_id=user_id)

        assert result == mock_session
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_session_key_found(self, mock_db_session):
        """Test get_by_session_key returns session when session FK found."""
        session_key = "session123"
        mock_session = MagicMock(spec=GuidedSessions)
        mock_session.session_key = session_key

        # Setup mock chain for execute().scalars().one_or_none()
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = mock_session
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await GuidedSessions.get_by_session_key(mock_db_session, session_key=session_key)

        assert result == mock_session
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_session_key_and_type_found(self, mock_db_session):
        """Test get_by_session_key_and_type returns session when found."""
        session_key = "session123"
        session_type = GuidedSessionType.ONBOARDING.value
        mock_session = MagicMock(spec=GuidedSessions)
        mock_session.session_key = session_key
        mock_session.session_type = session_type

        # Setup mock chain for execute().scalars().one_or_none()
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = mock_session
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await GuidedSessions.get_by_session_key_and_type(
            mock_db_session, session_key=session_key, session_type=session_type
        )

        assert result == mock_session
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_guided_session_key_found(self, mock_db_session):
        """Test get_by_guided_session_key returns session when found."""
        guided_session_key = "guided_session123"
        mock_session = MagicMock(spec=GuidedSessions)
        mock_session.guided_session_key = guided_session_key

        # Setup mock chain for execute().scalars().one_or_none()
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = mock_session
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await GuidedSessions.get_by_guided_session_key(
            mock_db_session, guided_session_key=guided_session_key
        )

        assert result == mock_session
        mock_db_session.execute.assert_called_once()


class TestBackwardCompatibility:
    """Test backward compatibility features."""

    def test_onboarding_session_alias(self):
        """Test OnboardingSession is an alias for GuidedSessions."""
        assert OnboardingSession is GuidedSessions

    def test_onboarding_state_alias(self):
        """Test OnboardingState is an alias for GuidedSessionState."""
        assert OnboardingState is GuidedSessionState

    def test_valid_onboarding_states_alias(self):
        """Test VALID_ONBOARDING_STATES is an alias."""
        assert VALID_ONBOARDING_STATES is VALID_GUIDED_SESSION_STATES

    def test_invalid_onboarding_state_error_compatibility(self):
        """Test InvalidOnboardingStateError backward compatibility."""
        error = InvalidOnboardingStateError("invalid_state")
        assert error.state == "invalid_state"
        assert "Invalid onboarding state: invalid_state" in str(error)
        assert isinstance(error, Exception)

    def test_generate_onboarding_key_compatibility(self, frozen_time):
        """Test generate_onboarding_key backward compatibility method."""
        user_id = "user123"
        started_at = frozen_time

        # Should produce same result as generate_guided_session_key with onboarding type
        expected = GuidedSessions.generate_guided_session_key(
            user_id, GuidedSessionType.ONBOARDING.value, started_at
        )
        result = GuidedSessions.generate_onboarding_key(user_id, started_at)

        assert result == expected

    @pytest.mark.asyncio
    async def test_start_onboarding_compatibility(self, mock_db_session):
        """Test start_onboarding backward compatibility method."""
        user_id = "user123"
        session_key = "session123"
        mock_session = MagicMock(spec=GuidedSessions)

        with patch.object(GuidedSessions, "start_guided_session", return_value=mock_session) as mock_start:
            result = await GuidedSessions.start_onboarding(
                mock_db_session, user_id=user_id, session_key=session_key
            )

        # Should call start_guided_session with onboarding type
        mock_start.assert_called_once_with(
            mock_db_session,
            user_id=user_id,
            session_key=session_key,
            session_type=GuidedSessionType.ONBOARDING.value,
        )
        assert result == mock_session

    @pytest.mark.asyncio
    async def test_end_onboarding_compatibility(self, mock_db_session, frozen_time):
        """Test end_onboarding backward compatibility method."""
        guided_session = GuidedSessions()

        with patch.object(guided_session, "end_guided_session") as mock_end:
            await guided_session.end_onboarding(mock_db_session, timestamp=frozen_time)

        mock_end.assert_called_once_with(mock_db_session, timestamp=frozen_time)

    @pytest.mark.asyncio
    async def test_inactivate_onboarding_compatibility(self, mock_db_session, frozen_time):
        """Test inactivate_onboarding backward compatibility method."""
        guided_session = GuidedSessions()

        with patch.object(guided_session, "inactivate_guided_session") as mock_inactivate:
            await guided_session.inactivate_onboarding(mock_db_session, timestamp=frozen_time)

        mock_inactivate.assert_called_once_with(mock_db_session, timestamp=frozen_time)

    @pytest.mark.asyncio
    async def test_get_by_onboarding_key_compatibility(self, mock_db_session):
        """Test get_by_onboarding_key backward compatibility method."""
        onboarding_key = "onboarding123"
        mock_session = MagicMock(spec=GuidedSessions)

        with patch.object(GuidedSessions, "get_by_guided_session_key", return_value=mock_session) as mock_get:
            result = await GuidedSessions.get_by_onboarding_key(
                mock_db_session, onboarding_key=onboarding_key
            )

        mock_get.assert_called_once_with(mock_db_session, guided_session_key=onboarding_key)
        assert result == mock_session

    def test_guided_session_key_consistency(self):
        """Test that guided session key generation is consistent for same inputs."""
        user_id = "user123"
        session_type = "onboarding"
        timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        key1 = GuidedSessions.generate_guided_session_key(user_id, session_type, timestamp)
        key2 = GuidedSessions.generate_guided_session_key(user_id, session_type, timestamp)

        assert key1 == key2

    def test_expiration_time_calculations(self):
        """Test various expiration time scenarios."""
        base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        with freeze_time(base_time):
            guided_session = GuidedSessions()
            guided_session.state = GuidedSessionState.ACTIVE.value

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
                guided_session.started_at = base_time - timedelta(minutes=minutes_ago)
                assert guided_session.is_expired == expected_expired, f"Failed for {minutes_ago} minutes ago"

    def test_state_property_transitions(self):
        """Test all state property combinations."""
        guided_session = GuidedSessions()

        # Test ACTIVE state
        guided_session.state = GuidedSessionState.ACTIVE.value
        assert guided_session.is_active is True
        assert guided_session.is_completed is False
        assert guided_session.is_incomplete is False

        # Test COMPLETE state
        guided_session.state = GuidedSessionState.COMPLETE.value
        assert guided_session.is_active is False
        assert guided_session.is_completed is True
        assert guided_session.is_incomplete is False

        # Test INCOMPLETE state
        guided_session.state = GuidedSessionState.INCOMPLETE.value
        assert guided_session.is_active is False
        assert guided_session.is_completed is False
        assert guided_session.is_incomplete is True
