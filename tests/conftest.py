"""Shared fixtures for data layer testing."""
# ruff: noqa: PLC0415

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import telegram
from freezegun import freeze_time
from sqlalchemy.ext.asyncio import AsyncSession

# Set test environment
os.environ["ENV"] = "test_env"
os.environ["CHAT_SESSION_TIMEOUT_MINS"] = "60"  # Set default timeout for tests


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

    # Patch AsyncDbSession to return our mock session (new path)
    with patch("areyouok_telegram.data.database.connection.AsyncDbSession") as mock_session_class:
        mock_session_class.return_value = session
        yield session


@pytest.fixture(autouse=True)
def frozen_time():
    """Freeze time for consistent testing - autouse for all tests."""
    with freeze_time(FROZEN_TIME):
        yield FROZEN_TIME


@pytest.fixture
def patch_async_database(monkeypatch, mock_db_session):
    """Patch areyouok_telegram.data.database.async_database to yield mock session."""

    class _Ctx:
        async def __aenter__(self):
            return mock_db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _factory():
        return _Ctx()

    monkeypatch.setattr(
        "areyouok_telegram.data.database.async_database",
        _factory,
        raising=True,
    )
    return mock_db_session


@pytest.fixture
def chat_factory():
    """Factory for creating a Chat with an encryption key and id set."""

    def _create(telegram_chat_id=1111, chat_type="private", *, id_value=1, with_key_mock=False):
        from unittest.mock import MagicMock

        from cryptography.fernet import Fernet

        from areyouok_telegram.data.models import Chat

        # Generate and set encrypted_key to satisfy validator
        encrypted_key = Chat.generate_encryption_key()
        chat = Chat(telegram_chat_id=telegram_chat_id, type=chat_type, id=id_value, encrypted_key=encrypted_key)

        if with_key_mock:
            # For tests needing to stub retrieve_key: provide a mock method
            key = Fernet.generate_key().decode()
            mock_retrieve = MagicMock(return_value=key)
            # Bypass Pydantic's immutability using __dict__
            chat.__dict__["retrieve_key"] = mock_retrieve
            return chat, key
        return chat

    return _create


@pytest.fixture
def user_factory():
    """Factory for creating a User instance."""

    def _create(telegram_user_id=2222, *, id_value=1, is_bot=False, language_code="en"):
        from areyouok_telegram.data.models import User

        return User(
            id=id_value,
            telegram_user_id=telegram_user_id,
            is_bot=is_bot,
            language_code=language_code,
        )

    return _create


@pytest.fixture
def session_factory(chat_factory):
    """Factory for creating a Session instance bound to a Chat."""

    def _create(chat=None, *, id_value=1, session_start=None):
        from datetime import UTC, datetime

        from areyouok_telegram.data.models import Session

        chat = chat or chat_factory()
        session_start = session_start or datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        return Session(id=id_value, chat=chat, session_start=session_start)

    return _create


@pytest.fixture
def mock_active_session(chat_factory):
    """Create a mock active session for testing handlers."""
    # Use MagicMock to allow tests to access both .id and .session_id
    session = MagicMock()
    session.id = 123
    session.session_id = "123"  # String version for legacy tests
    session.chat_id = 456
    session.session_start = FROZEN_TIME
    session.last_user_activity = FROZEN_TIME
    session.last_bot_activity = FROZEN_TIME
    session.message_count = 0
    return session


@pytest.fixture
def mock_telegram_user():
    """Create a mock Telegram user."""
    user = MagicMock(spec=telegram.User)
    user.id = 123456789
    user.is_bot = False
    user.language_code = "en"
    user.is_premium = True
    user.username = "testuser"
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
    message.caption = None
    message.edit_date = None
    return message
