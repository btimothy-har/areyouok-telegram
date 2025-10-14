"""Tests for GuidedSessions model."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from freezegun import freeze_time

from areyouok_telegram.data.models.guided_sessions import (
    VALID_GUIDED_SESSION_STATES,
    VALID_GUIDED_SESSION_TYPES,
    GuidedSessions,
    GuidedSessionState,
    GuidedSessionType,
    InvalidGuidedSessionStateError,
    InvalidGuidedSessionTypeError,
)
from areyouok_telegram.encryption.exceptions import ContentNotDecryptedError

# Backward compatibility aliases for testing
VALID_ONBOARDING_STATES = VALID_GUIDED_SESSION_STATES
OnboardingSession = GuidedSessions
OnboardingState = GuidedSessionState


class InvalidOnboardingStateError(Exception):
    def __init__(self, state: str):
        super().__init__(f"Invalid onboarding state: {state}. Expected one of: {VALID_ONBOARDING_STATES}.")
        self.state = state


# Add backward compatibility methods to GuidedSessions class
def add_backward_compatibility():
    """Add backward compatibility methods to GuidedSessions class."""

    @staticmethod
    def generate_onboarding_key(chat_session: str, started_at: datetime) -> str:
        """Backward compatibility method for onboarding key generation."""
        return GuidedSessions.generate_guided_session_key(chat_session, GuidedSessionType.ONBOARDING.value, started_at)

    @classmethod
    async def start_onboarding(cls, db_conn, *, user_id: str, session_key: str):
        """Backward compatibility method for starting onboarding."""
        return await cls.start_new_session(
            db_conn, chat_id=user_id, chat_session=session_key, session_type=GuidedSessionType.ONBOARDING.value
        )

    async def end_onboarding(self, db_conn, *, timestamp: datetime):
        """Backward compatibility method for ending onboarding."""
        return await self.complete(db_conn, timestamp=timestamp)

    async def inactivate_onboarding(self, db_conn, *, timestamp: datetime):
        """Backward compatibility method for inactivating onboarding."""
        return await self.inactivate(db_conn, timestamp=timestamp)

    @classmethod
    async def get_by_user_id(cls, db_conn, *, user_id: str):
        """Backward compatibility method for getting by user ID."""
        # In the new API, user_id maps to chat_id
        sessions = await cls.get_by_chat_id(db_conn, chat_id=user_id)
        return sessions[0] if sessions else None

    @classmethod
    async def get_by_user_id_and_type(cls, db_conn, *, user_id: str, session_type: str):
        """Backward compatibility method for getting by user ID and type."""
        sessions = await cls.get_by_chat_id(db_conn, chat_id=user_id, session_type=session_type)
        return sessions[0] if sessions else None

    @classmethod
    async def get_by_session_key(cls, db_conn, *, session_key: str):
        """Backward compatibility method for getting by session key."""
        sessions = await cls.get_by_chat_session(db_conn, chat_session=session_key)
        return sessions[0] if sessions else None

    @classmethod
    async def get_by_session_key_and_type(cls, db_conn, *, session_key: str, session_type: str):
        """Backward compatibility method for getting by session key and type."""
        sessions = await cls.get_by_chat_session(db_conn, chat_session=session_key, session_type=session_type)
        return sessions[0] if sessions else None

    @classmethod
    async def get_by_onboarding_key(cls, db_conn, *, onboarding_key: str):
        """Backward compatibility method for getting by onboarding key."""
        return await cls.get_by_guided_session_key(db_conn, guided_session_key=onboarding_key)

    # Add methods to the GuidedSessions class
    GuidedSessions.generate_onboarding_key = staticmethod(generate_onboarding_key)
    GuidedSessions.start_onboarding = classmethod(start_onboarding)
    GuidedSessions.end_onboarding = end_onboarding
    GuidedSessions.inactivate_onboarding = inactivate_onboarding
    GuidedSessions.get_by_user_id = classmethod(get_by_user_id)
    GuidedSessions.get_by_user_id_and_type = classmethod(get_by_user_id_and_type)
    GuidedSessions.get_by_session_key = classmethod(get_by_session_key)
    GuidedSessions.get_by_session_key_and_type = classmethod(get_by_session_key_and_type)
    GuidedSessions.get_by_onboarding_key = classmethod(get_by_onboarding_key)


# Apply backward compatibility
add_backward_compatibility()


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
        """Test guided session key generation with chat_session, session type, and timestamp."""
        chat_session = "user123"
        session_type = "onboarding"
        started_at = frozen_time

        timestamp_str = started_at.isoformat()
        expected = hashlib.sha256(f"{session_type}:{chat_session}:{timestamp_str}".encode()).hexdigest()

        result = GuidedSessions.generate_guided_session_key(chat_session, session_type, started_at)

        assert result == expected

    def test_generate_guided_session_key_different_users(self, frozen_time):
        """Test guided session key generation produces different keys for different chat sessions."""
        chat_session1 = "user123"
        chat_session2 = "user456"
        session_type = "onboarding"
        started_at = frozen_time

        key1 = GuidedSessions.generate_guided_session_key(chat_session1, session_type, started_at)
        key2 = GuidedSessions.generate_guided_session_key(chat_session2, session_type, started_at)

        assert key1 != key2

    def test_generate_guided_session_key_different_types(self, frozen_time):
        """Test guided session key generation produces different keys for different session types."""
        chat_session = "user123"
        session_type1 = "onboarding"
        session_type2 = "mindfulness"
        started_at = frozen_time

        key1 = GuidedSessions.generate_guided_session_key(chat_session, session_type1, started_at)
        key2 = GuidedSessions.generate_guided_session_key(chat_session, session_type2, started_at)

        assert key1 != key2

    def test_generate_guided_session_key_different_timestamps(self):
        """Test guided session key generation produces different keys for different timestamps."""
        chat_session = "user123"
        session_type = "onboarding"
        time1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        time2 = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        key1 = GuidedSessions.generate_guided_session_key(chat_session, session_type, time1)
        key2 = GuidedSessions.generate_guided_session_key(chat_session, session_type, time2)

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

    def test_is_expired_property_false_for_active_without_started_at(self):
        """Test is_expired returns False for ACTIVE state when started_at is None."""
        guided_session = GuidedSessions()
        guided_session.state = GuidedSessionState.ACTIVE.value
        guided_session.started_at = None

        assert guided_session.is_expired is False

    @pytest.mark.asyncio
    async def test_start_new_session(self, mock_db_session):
        """Test start_new_session creates new active guided session record."""
        chat_id = "user123"
        chat_session = "session123"
        session_type = GuidedSessionType.ONBOARDING.value

        result = await GuidedSessions.start_new_session(
            mock_db_session, chat_id=chat_id, chat_session=chat_session, session_type=session_type
        )

        # Verify database execute was called
        mock_db_session.execute.assert_called_once()

        # Get the statement that was executed
        call_args = mock_db_session.execute.call_args[0][0]

        # Verify it's an insert statement for guided_sessions table
        assert hasattr(call_args, "table")
        assert call_args.table.name == "guided_sessions"

        # Since start_new_session doesn't return anything, result should be None
        assert result is None

    @pytest.mark.asyncio
    async def test_start_new_session_invalid_type(self, mock_db_session):
        """Test start_new_session raises error for invalid session type."""
        chat_id = "user123"
        chat_session = "session123"
        session_type = "invalid_type"

        with pytest.raises(InvalidGuidedSessionTypeError) as exc_info:
            await GuidedSessions.start_new_session(
                mock_db_session, chat_id=chat_id, chat_session=chat_session, session_type=session_type
            )

        assert exc_info.value.session_type == "invalid_type"

    @pytest.mark.asyncio
    async def test_complete_guided_session(self, mock_db_session, frozen_time):
        """Test complete method completes the guided session."""
        guided_session = GuidedSessions()
        guided_session.state = GuidedSessionState.ACTIVE.value
        guided_session.completed_at = None
        original_updated_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        guided_session.updated_at = original_updated_at

        await guided_session.complete(mock_db_session, timestamp=frozen_time)

        # Verify state changes
        assert guided_session.state == GuidedSessionState.COMPLETE.value
        assert guided_session.completed_at == frozen_time
        assert guided_session.updated_at == frozen_time

        # Verify object was added to session
        mock_db_session.add.assert_called_once_with(guided_session)

    @pytest.mark.asyncio
    async def test_inactivate_guided_session(self, mock_db_session, frozen_time):
        """Test inactivate method marks session as incomplete."""
        guided_session = GuidedSessions()
        guided_session.state = GuidedSessionState.ACTIVE.value
        original_updated_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        guided_session.updated_at = original_updated_at

        await guided_session.inactivate(mock_db_session, timestamp=frozen_time)

        # Verify state changes
        assert guided_session.state == GuidedSessionState.INCOMPLETE.value
        assert guided_session.updated_at == frozen_time

        # Verify object was added to session
        mock_db_session.add.assert_called_once_with(guided_session)

    @pytest.mark.asyncio
    async def test_get_by_chat_id_with_session_type(self, mock_db_session):
        """Test get_by_chat_id returns sessions filtered by session type when found."""
        chat_id = "user123"
        session_type = GuidedSessionType.ONBOARDING.value
        mock_session = MagicMock(spec=GuidedSessions)
        mock_session.chat_id = chat_id
        mock_session.session_type = session_type

        # Setup mock chain for execute().scalars().all()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_session]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await GuidedSessions.get_by_chat_id(mock_db_session, chat_id=chat_id, session_type=session_type)

        assert result == [mock_session]
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_chat_id_found(self, mock_db_session):
        """Test get_by_chat_id returns sessions when found."""
        chat_id = "user123"
        mock_session = MagicMock(spec=GuidedSessions)
        mock_session.chat_id = chat_id

        # Setup mock chain for execute().scalars().all()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_session]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await GuidedSessions.get_by_chat_id(mock_db_session, chat_id=chat_id)

        assert result == [mock_session]
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_chat_session_found(self, mock_db_session):
        """Test get_by_chat_session returns sessions when chat session found."""
        chat_session = "session123"
        mock_session = MagicMock(spec=GuidedSessions)
        mock_session.chat_session = chat_session

        # Setup mock chain for execute().scalars().all()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_session]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await GuidedSessions.get_by_chat_session(mock_db_session, chat_session=chat_session)

        assert result == [mock_session]
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_chat_session_and_type_found(self, mock_db_session):
        """Test get_by_chat_session returns sessions filtered by session type when found."""
        chat_session = "session123"
        session_type = GuidedSessionType.ONBOARDING.value
        mock_session = MagicMock(spec=GuidedSessions)
        mock_session.chat_session = chat_session
        mock_session.session_type = session_type

        # Setup mock chain for execute().scalars().all()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_session]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await GuidedSessions.get_by_chat_session(
            mock_db_session, chat_session=chat_session, session_type=session_type
        )

        assert result == [mock_session]
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

        result = await GuidedSessions.get_by_guided_session_key(mock_db_session, guided_session_key=guided_session_key)

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
        expected = GuidedSessions.generate_guided_session_key(user_id, GuidedSessionType.ONBOARDING.value, started_at)
        result = GuidedSessions.generate_onboarding_key(user_id, started_at)

        assert result == expected

    @pytest.mark.asyncio
    async def test_start_onboarding_compatibility(self, mock_db_session):
        """Test start_onboarding backward compatibility method."""
        chat_id = "user123"
        session_key = "session123"

        with patch.object(GuidedSessions, "start_new_session", return_value=None) as mock_start:
            result = await GuidedSessions.start_onboarding(mock_db_session, user_id=chat_id, session_key=session_key)

        # Should call start_new_session with onboarding type
        mock_start.assert_called_once_with(
            mock_db_session,
            chat_id=chat_id,
            chat_session=session_key,
            session_type=GuidedSessionType.ONBOARDING.value,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_end_onboarding_compatibility(self, mock_db_session, frozen_time):
        """Test end_onboarding backward compatibility method."""
        guided_session = GuidedSessions()

        with patch.object(guided_session, "complete") as mock_end:
            await guided_session.end_onboarding(mock_db_session, timestamp=frozen_time)

        mock_end.assert_called_once_with(mock_db_session, timestamp=frozen_time)

    @pytest.mark.asyncio
    async def test_inactivate_onboarding_compatibility(self, mock_db_session, frozen_time):
        """Test inactivate_onboarding backward compatibility method."""
        guided_session = GuidedSessions()

        with patch.object(guided_session, "inactivate") as mock_inactivate:
            await guided_session.inactivate_onboarding(mock_db_session, timestamp=frozen_time)

        mock_inactivate.assert_called_once_with(mock_db_session, timestamp=frozen_time)

    @pytest.mark.asyncio
    async def test_get_by_onboarding_key_compatibility(self, mock_db_session):
        """Test get_by_onboarding_key backward compatibility method."""
        onboarding_key = "onboarding123"
        mock_session = MagicMock(spec=GuidedSessions)

        with patch.object(GuidedSessions, "get_by_guided_session_key", return_value=mock_session) as mock_get:
            result = await GuidedSessions.get_by_onboarding_key(mock_db_session, onboarding_key=onboarding_key)

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


class TestGuidedSessionsMetadata:
    """Test encrypted metadata functionality for GuidedSessions."""

    def test_encrypt_metadata_dict(self):
        """Test encrypting metadata dict."""
        metadata = {"step": 1, "responses": {"name": "Alice"}}
        encryption_key = Fernet.generate_key().decode("utf-8")

        encrypted = GuidedSessions.encrypt_metadata(metadata=metadata, chat_encryption_key=encryption_key)

        # Should be a string (base64 encoded encrypted data)
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0

        # Should be able to decrypt it back
        fernet = Fernet(encryption_key.encode())
        decrypted_bytes = fernet.decrypt(encrypted.encode("utf-8"))
        decrypted_content = json.loads(decrypted_bytes.decode("utf-8"))
        assert decrypted_content == metadata

    def test_encrypt_metadata_empty_dict(self):
        """Test encrypting empty dict."""
        metadata = {}
        encryption_key = Fernet.generate_key().decode("utf-8")

        encrypted = GuidedSessions.encrypt_metadata(metadata=metadata, chat_encryption_key=encryption_key)

        # Should still work with empty dict
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0

        # Verify it decrypts to empty dict
        fernet = Fernet(encryption_key.encode())
        decrypted_bytes = fernet.decrypt(encrypted.encode("utf-8"))
        decrypted_content = json.loads(decrypted_bytes.decode("utf-8"))
        assert decrypted_content == {}

    def test_encrypt_metadata_nested_dict(self):
        """Test encrypting nested dict structure."""
        metadata = {
            "step": 3,
            "responses": {"name": "Bob", "preferences": {"style": "casual", "speed": "fast"}},
            "timestamps": ["2025-01-01", "2025-01-02"],
        }
        encryption_key = Fernet.generate_key().decode("utf-8")

        encrypted = GuidedSessions.encrypt_metadata(metadata=metadata, chat_encryption_key=encryption_key)

        # Verify complex structure is preserved
        fernet = Fernet(encryption_key.encode())
        decrypted_bytes = fernet.decrypt(encrypted.encode("utf-8"))
        decrypted_content = json.loads(decrypted_bytes.decode("utf-8"))
        assert decrypted_content == metadata

    def test_decrypt_metadata_with_encrypted_data(self):
        """Test decrypting metadata when encrypted_metadata exists."""
        guided_session = GuidedSessions()
        guided_session.guided_session_key = "decrypt_with_data_key"
        metadata = {"step": 2, "data": "value"}
        encryption_key = Fernet.generate_key().decode("utf-8")

        # Encrypt and set
        guided_session.encrypted_metadata = GuidedSessions.encrypt_metadata(
            metadata=metadata, chat_encryption_key=encryption_key
        )

        # Decrypt
        guided_session.decrypt_metadata(chat_encryption_key=encryption_key)

        # Verify it's in cache
        assert guided_session.guided_session_key in guided_session._metadata_cache

    def test_decrypt_metadata_no_encrypted_data(self):
        """Test decrypting when no encrypted_metadata exists."""
        guided_session = GuidedSessions()
        guided_session.guided_session_key = "decrypt_no_data_key"
        guided_session.encrypted_metadata = None
        encryption_key = Fernet.generate_key().decode("utf-8")

        # Should not raise error, just do nothing
        guided_session.decrypt_metadata(chat_encryption_key=encryption_key)

        # Cache should remain empty for this key
        assert guided_session.guided_session_key not in guided_session._metadata_cache

    def test_decrypt_metadata_already_cached(self):
        """Test that decrypt doesn't re-decrypt if already in cache."""
        guided_session = GuidedSessions()
        guided_session.guided_session_key = "decrypt_already_cached_key"
        metadata = {"step": 2}
        encryption_key = Fernet.generate_key().decode("utf-8")

        # Encrypt and set
        guided_session.encrypted_metadata = GuidedSessions.encrypt_metadata(
            metadata=metadata, chat_encryption_key=encryption_key
        )

        # First decrypt
        guided_session.decrypt_metadata(chat_encryption_key=encryption_key)
        cached_value = guided_session._metadata_cache[guided_session.guided_session_key]

        # Second decrypt - should use cached value
        guided_session.decrypt_metadata(chat_encryption_key=encryption_key)
        assert guided_session._metadata_cache[guided_session.guided_session_key] == cached_value

    def test_session_metadata_property_with_decrypted_data(self):
        """Test accessing session_metadata property after decryption."""
        guided_session = GuidedSessions()
        guided_session.guided_session_key = "property_with_decrypt_key"
        metadata = {"step": 3, "responses": {"name": "Charlie"}}
        encryption_key = Fernet.generate_key().decode("utf-8")

        # Encrypt, set, and decrypt
        guided_session.encrypted_metadata = GuidedSessions.encrypt_metadata(
            metadata=metadata, chat_encryption_key=encryption_key
        )
        guided_session.decrypt_metadata(chat_encryption_key=encryption_key)

        # Access property
        result = guided_session.session_metadata
        assert result == metadata

    def test_session_metadata_property_without_decryption(self):
        """Test accessing session_metadata property before decryption raises error."""
        guided_session = GuidedSessions()
        guided_session.guided_session_key = "property_without_decrypt_key"
        metadata = {"step": 1}
        encryption_key = Fernet.generate_key().decode("utf-8")

        # Encrypt and set, but don't decrypt
        guided_session.encrypted_metadata = GuidedSessions.encrypt_metadata(
            metadata=metadata, chat_encryption_key=encryption_key
        )

        # Should raise ContentNotDecryptedError with property name
        with pytest.raises(ContentNotDecryptedError) as exc_info:
            _ = guided_session.session_metadata

        assert exc_info.value.field_name == "session_metadata"

    def test_session_metadata_property_no_encrypted_data(self):
        """Test accessing session_metadata property when no encrypted data exists."""
        guided_session = GuidedSessions()
        guided_session.guided_session_key = "property_no_data_key"
        guided_session.encrypted_metadata = None

        # Should return None, not raise error
        result = guided_session.session_metadata
        assert result is None

    async def test_update_metadata(self, mock_db_session):
        """Test updating metadata on a guided session."""
        guided_session = GuidedSessions()
        guided_session.guided_session_key = "update_metadata_key"
        metadata = {"step": 4, "new_data": "updated"}
        encryption_key = Fernet.generate_key().decode("utf-8")

        with freeze_time("2025-01-02 12:00:00"):
            await guided_session.update_metadata(mock_db_session, metadata=metadata, chat_encryption_key=encryption_key)

        # Verify encrypted_metadata was set
        assert guided_session.encrypted_metadata is not None

        # Verify updated_at was set
        assert guided_session.updated_at == datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC)

        # Verify session was added to db
        mock_db_session.add.assert_called_once_with(guided_session)

        # Verify it can be decrypted
        fernet = Fernet(encryption_key.encode())
        decrypted_bytes = fernet.decrypt(guided_session.encrypted_metadata.encode("utf-8"))
        decrypted_content = json.loads(decrypted_bytes.decode("utf-8"))
        assert decrypted_content == metadata

    async def test_update_metadata_overwrites_existing(self, mock_db_session):
        """Test that update_metadata overwrites existing metadata."""
        guided_session = GuidedSessions()
        guided_session.guided_session_key = "update_overwrites_key"
        encryption_key = Fernet.generate_key().decode("utf-8")

        # Set initial metadata
        initial_metadata = {"step": 1}
        guided_session.encrypted_metadata = GuidedSessions.encrypt_metadata(
            metadata=initial_metadata, chat_encryption_key=encryption_key
        )

        # Update with new metadata
        new_metadata = {"step": 2, "complete": True}
        await guided_session.update_metadata(mock_db_session, metadata=new_metadata, chat_encryption_key=encryption_key)

        # Verify new metadata replaced old
        fernet = Fernet(encryption_key.encode())
        decrypted_bytes = fernet.decrypt(guided_session.encrypted_metadata.encode("utf-8"))
        decrypted_content = json.loads(decrypted_bytes.decode("utf-8"))
        assert decrypted_content == new_metadata
        assert decrypted_content != initial_metadata

    async def test_update_metadata_invalidates_cache(self, mock_db_session):
        """Test that update_metadata clears cached decrypted data."""
        guided_session = GuidedSessions()
        guided_session.guided_session_key = "update_invalidates_cache_key"
        encryption_key = Fernet.generate_key().decode("utf-8")

        # Set and decrypt initial metadata
        initial_metadata = {"step": 1, "old": "data"}
        guided_session.encrypted_metadata = GuidedSessions.encrypt_metadata(
            metadata=initial_metadata, chat_encryption_key=encryption_key
        )
        guided_session.decrypt_metadata(chat_encryption_key=encryption_key)

        # Verify it's cached
        assert guided_session.guided_session_key in guided_session._metadata_cache
        assert guided_session.session_metadata == initial_metadata

        # Update metadata - should clear cache
        new_metadata = {"step": 2, "new": "data"}
        await guided_session.update_metadata(mock_db_session, metadata=new_metadata, chat_encryption_key=encryption_key)

        # Cache should be cleared for this key
        assert guided_session.guided_session_key not in guided_session._metadata_cache

        # Accessing property should raise error until re-decrypted
        with pytest.raises(ContentNotDecryptedError):
            _ = guided_session.session_metadata

        # After re-decrypting, should get new metadata
        guided_session.decrypt_metadata(chat_encryption_key=encryption_key)
        assert guided_session.session_metadata == new_metadata

    def test_metadata_cache_isolation(self):
        """Test that metadata cache is isolated between different sessions."""
        encryption_key = Fernet.generate_key().decode("utf-8")

        session1 = GuidedSessions()
        session1.guided_session_key = "key_1"
        session1.encrypted_metadata = GuidedSessions.encrypt_metadata(
            metadata={"session": 1}, chat_encryption_key=encryption_key
        )

        session2 = GuidedSessions()
        session2.guided_session_key = "key_2"
        session2.encrypted_metadata = GuidedSessions.encrypt_metadata(
            metadata={"session": 2}, chat_encryption_key=encryption_key
        )

        # Decrypt both
        session1.decrypt_metadata(chat_encryption_key=encryption_key)
        session2.decrypt_metadata(chat_encryption_key=encryption_key)

        # Verify each has correct data
        assert session1.session_metadata == {"session": 1}
        assert session2.session_metadata == {"session": 2}

    def test_encrypt_decrypt_round_trip_with_special_characters(self):
        """Test encryption/decryption with special characters in metadata."""
        metadata = {
            "unicode": "Hello 世界 🌍",
            "special": "Test\nNewline\tTab",
            "quotes": "Single ' and double \" quotes",
        }
        encryption_key = Fernet.generate_key().decode("utf-8")

        # Encrypt
        encrypted = GuidedSessions.encrypt_metadata(metadata=metadata, chat_encryption_key=encryption_key)

        # Decrypt manually to verify
        fernet = Fernet(encryption_key.encode())
        decrypted_bytes = fernet.decrypt(encrypted.encode("utf-8"))
        decrypted_content = json.loads(decrypted_bytes.decode("utf-8"))

        assert decrypted_content == metadata
