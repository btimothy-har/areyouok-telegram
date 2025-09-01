"""Additional tests for Sessions model."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from areyouok_telegram.data.models.sessions import Sessions


class TestSessionsOnboardingIntegration:
    """Test Sessions model integration with onboarding functionality."""

    @pytest.mark.asyncio
    async def test_get_onboarding_found(self, mock_db_session):
        """Test get_onboarding method when onboarding session exists."""
        session = Sessions()
        session.session_key = "test_session_key_123"

        # Mock the OnboardingSession.get_by_session_key method
        from areyouok_telegram.data.models.guided_sessions import OnboardingSession
        mock_onboarding = MagicMock(spec=OnboardingSession)

        with patch.object(OnboardingSession, "get_by_session_key", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_onboarding

            result = await session.get_onboarding(mock_db_session)

            assert result == mock_onboarding
            mock_get.assert_called_once_with(mock_db_session, session_key=session.session_key)

    @pytest.mark.asyncio
    async def test_get_onboarding_not_found(self, mock_db_session):
        """Test get_onboarding method when no onboarding session exists."""
        session = Sessions()
        session.session_key = "test_session_key_456"

        # Mock the OnboardingSession.get_by_session_key method
        from areyouok_telegram.data.models.guided_sessions import OnboardingSession

        with patch.object(OnboardingSession, "get_by_session_key", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await session.get_onboarding(mock_db_session)

            assert result is None
            mock_get.assert_called_once_with(mock_db_session, session_key=session.session_key)
