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


@pytest.fixture
def mock_messages_sqlalchemy():
    """Create a mock Messages SQLAlchemy object."""
    from areyouok_telegram.data.models.messages import Messages

    mock_message = MagicMock(spec=Messages)
    mock_message.message_type = "Message"
    mock_message.message_id = "123"
    mock_message.user_id = "user123"
    mock_message.reasoning = None
    return mock_message


@pytest.fixture
def mock_context_sqlalchemy():
    """Create a mock Context SQLAlchemy object."""
    from areyouok_telegram.data.models.context import Context, ContextType

    mock_context = MagicMock(spec=Context)
    mock_context.type = ContextType.SESSION.value
    mock_context.content = "Test context content"
    mock_context.created_at = FROZEN_TIME
    return mock_context


@pytest.fixture
def mock_media_files():
    """Factory for creating mock MediaFiles objects."""

    def _create(count=1, mime_type="image/png", *, is_anthropic_supported=True, is_openai_google_supported=None):
        from areyouok_telegram.data.models.media import MediaFiles

        # If is_openai_google_supported is not specified, use the same value as is_anthropic_supported
        if is_openai_google_supported is None:
            is_openai_google_supported = is_anthropic_supported

        files = []
        for _i in range(count):
            mock_file = MagicMock(spec=MediaFiles)
            mock_file.mime_type = mime_type
            mock_file.is_anthropic_supported = is_anthropic_supported
            mock_file.is_openai_google_supported = is_openai_google_supported
            mock_file.bytes_data = b"fake image data"
            files.append(mock_file)
        return files if count > 1 else files[0]

    return _create


@pytest.fixture
def mock_chat_event_message(mock_messages_sqlalchemy, mock_telegram_message):
    """Factory for creating message-type ChatEvents."""

    def _create(text="Test message", message_id="123", user_id="user123", attachments=None):
        from areyouok_telegram.data.models.chat_event import ChatEvent

        # Update mock objects with provided values
        mock_messages_sqlalchemy.message_id = message_id
        mock_messages_sqlalchemy.user_id = user_id
        mock_telegram_message.text = text
        mock_telegram_message.message_id = int(message_id)
        mock_messages_sqlalchemy.telegram_object = mock_telegram_message

        attachments = attachments or []
        return ChatEvent.from_message(mock_messages_sqlalchemy, attachments)

    return _create


@pytest.fixture
def mock_chat_event_context(mock_context_sqlalchemy):
    """Factory for creating context-type ChatEvents."""

    def _create(content="Context content", context_type=None):
        from areyouok_telegram.data.models.chat_event import ChatEvent

        if context_type:
            mock_context_sqlalchemy.type = context_type.value
        mock_context_sqlalchemy.content = content

        return ChatEvent.from_context(mock_context_sqlalchemy)

    return _create


@pytest.fixture
def mock_conversation_history(mock_chat_event_message, mock_chat_event_context):
    """Create a mock conversation history with mixed events."""

    def _create(message_count=2, context_count=1):
        from areyouok_telegram.data.models.context import ContextType

        events = []

        # Add context events
        events.extend(
            [
                mock_chat_event_context(content=f"Context {i + 1}", context_type=ContextType.SESSION)
                for i in range(context_count)
            ]
        )

        # Add message events
        events.extend(
            [
                mock_chat_event_message(text=f"Message {i + 1}", message_id=str(100 + i), user_id=f"user{i + 1}")
                for i in range(message_count)
            ]
        )

        return events

    return _create


@pytest.fixture
def mock_active_session():
    """Create a mock active session for testing."""
    from areyouok_telegram.data.models.sessions import Sessions

    session = MagicMock(spec=Sessions)
    session.session_id = "test_session_123"
    session.chat_id = "test_chat_456"
    session.user_id = "test_user_789"
    session.created_at = FROZEN_TIME
    session.last_user_activity = FROZEN_TIME
    session.last_bot_activity = FROZEN_TIME
    session.is_active = True

    # Mock the get_messages method
    session.get_messages = AsyncMock(return_value=[])

    return session


@pytest.fixture
def mock_chat_with_key():
    """Create a mock chat with encryption key for testing."""
    from areyouok_telegram.data.models.chats import Chats

    chat = MagicMock(spec=Chats)
    chat.chat_id = "test_chat_456"
    chat.user_id = "test_user_789"
    chat.created_at = FROZEN_TIME

    # Mock encryption key methods
    chat.retrieve_key = MagicMock(return_value=b"test_encryption_key")

    return chat


@pytest.fixture
def mock_context_items():
    """Create mock context items for testing."""
    from areyouok_telegram.data.models.context import Context, ContextType

    contexts = []
    for i in range(3):
        context = MagicMock(spec=Context)
        context.session_id = "test_session_123"
        context.type = ContextType.USER_PREFERENCE.value  # Not SESSION type
        context.content = f"Context content {i}"
        context.created_at = FROZEN_TIME
        context.decrypt_content = MagicMock()
        contexts.append(context)

    return contexts


@pytest.fixture
def mock_media_files_list():
    """Create a list of mock media files for testing."""
    from areyouok_telegram.data.models.media import MediaFiles

    media_files = []
    for i in range(2):
        media = MagicMock(spec=MediaFiles)
        media.message_id = f"msg_{i}"
        media.chat_id = "test_chat_456"
        media.file_type = "image"
        media.mime_type = "image/png"
        media.decrypt_content = MagicMock()
        media_files.append(media)

    return media_files


@pytest.fixture
def mock_messages_list():
    """Create a list of mock messages for testing."""
    from areyouok_telegram.data.models.messages import Messages

    messages = []
    for i in range(15):  # Sufficient for feedback context (>10)
        message = MagicMock(spec=Messages)
        message.message_id = f"msg_{i}"
        message.chat_id = "test_chat_456"
        message.user_id = "test_user_789" if i % 2 == 0 else "bot_user"
        message.message_type = "Message" if i % 2 == 0 else "MessageReactionUpdated"
        message.content = f"Message content {i}"
        message.created_at = FROZEN_TIME
        message.decrypt = MagicMock()
        messages.append(message)

    return messages
