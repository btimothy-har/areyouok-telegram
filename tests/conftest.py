"""Shared fixtures for data layer testing."""

import os
from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

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
    def _create(count=1, mime_type="image/png", is_anthropic_supported=True):
        from areyouok_telegram.data.models.media import MediaFiles
        
        files = []
        for i in range(count):
            mock_file = MagicMock(spec=MediaFiles)
            mock_file.mime_type = mime_type
            mock_file.is_anthropic_supported = is_anthropic_supported
            mock_file.bytes_data = b"fake image data"
            files.append(mock_file)
        return files if count > 1 else files[0]
    return _create


@pytest.fixture
def mock_chat_event_message(mock_messages_sqlalchemy, mock_telegram_message, mock_media_files):
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
        from areyouok_telegram.data.models.context import ContextType
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
        for i in range(context_count):
            events.append(mock_chat_event_context(
                content=f"Context {i+1}",
                context_type=ContextType.SESSION
            ))
        
        # Add message events
        for i in range(message_count):
            events.append(mock_chat_event_message(
                text=f"Message {i+1}",
                message_id=str(100 + i),
                user_id=f"user{i+1}"
            ))
        
        return events
    return _create
