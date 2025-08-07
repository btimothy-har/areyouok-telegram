"""Shared fixtures for data layer testing."""

from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from freezegun import freeze_time
from sqlalchemy.ext.asyncio import AsyncSession

FROZEN_TIME = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def mock_db_session():
    """Mock async database session for unit testing - autouse for all tests."""
    session = AsyncMock(spec=AsyncSession)

    # Mock async methods
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    # Mock sync methods
    session.add = MagicMock()
    session.delete = MagicMock()
    session.merge = MagicMock()

    # Patch AsyncDbSession to return our mock session
    with patch("areyouok_telegram.data.connection.AsyncDbSession") as mock_session_class:
        mock_session_class.return_value = session
        yield session


@pytest.fixture(autouse=True)
def frozen_time():
    """Freeze time for consistent testing - autouse for all tests."""
    with freeze_time(FROZEN_TIME):
        yield FROZEN_TIME


@pytest.fixture
def mock_telegram_user():
    """Create a mock Telegram user."""
    user = MagicMock(spec=telegram.User)
    user.id = 123456789
    user.is_bot = False
    user.language_code = "en"
    user.is_premium = True
    return user


@pytest.fixture
def mock_telegram_chat():
    """Create a mock Telegram private chat."""
    chat = MagicMock(spec=telegram.Chat)
    chat.id = 987654321
    chat.type = "private"
    chat.title = None
    chat.is_forum = False
    return chat


@pytest.fixture
def mock_telegram_message(mock_telegram_user, mock_telegram_chat):
    """Create a mock Telegram message."""
    message = MagicMock(spec=telegram.Message)
    message.message_id = 42
    message.from_user = mock_telegram_user
    message.chat = mock_telegram_chat
    message.date = FROZEN_TIME
    message.text = "Test message"
    message.edit_date = None
    return message
