"""Pytest configuration and shared fixtures for telegram bot testing."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import create_autospec
from unittest.mock import patch

import pydantic_ai
import pytest
import telegram

from areyouok_telegram.data import Sessions

DEFAULT_DATETIME = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def prevent_model_requests():
    """Prevent accidental requests to real LLM models during testing."""
    # This global setting prevents any real model requests
    pydantic_ai.models.ALLOW_MODEL_REQUESTS = False
    yield
    # Reset to default after test
    pydantic_ai.models.ALLOW_MODEL_REQUESTS = True


@pytest.fixture(autouse=True)
def async_database_connection():
    """
    Fixture that provides a mock async database session for all tests.

    This fixture automatically mocks the database session to prevent tests
    from requiring an actual database connection. The mock session can be
    configured within individual tests to return specific data.
    """
    mock_session = AsyncMock()

    # Mock common session methods - async ones
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    # Mock synchronous session methods
    mock_session.add = MagicMock()
    mock_session.delete = MagicMock()

    with patch("areyouok_telegram.data.connection.AsyncDbSession") as mock_session_class:
        mock_session_class.return_value = mock_session
        yield mock_session


@pytest.fixture
def mock_user():
    """Create a mock telegram.User object."""
    mock_user = create_autospec(telegram.User, spec_set=True, instance=True)

    mock_user.id = 987654321
    mock_user.first_name = "John"
    mock_user.last_name = "Doe"
    mock_user.username = "johndoe"
    mock_user.is_bot = False
    mock_user.language_code = "en"

    # Configure the full_name property to return the expected value
    mock_user.full_name = "John Doe"
    mock_user.link = "https://t.me/johndoe"

    return mock_user


@pytest.fixture
def mock_private_chat():
    """Create a mock telegram.Chat object."""
    mock_chat = create_autospec(telegram.Chat, spec_set=True, instance=True)

    mock_chat.id = 123456789
    mock_chat.type = "private"
    mock_chat.username = "johndoe"
    mock_chat.first_name = "John"
    mock_chat.last_name = "Doe"

    # Set computed properties
    mock_chat.full_name = "John Doe"
    mock_chat.link = "https://t.me/johndoe"

    return mock_chat


@pytest.fixture
def mock_group_chat():
    """Create a mock telegram.Chat object."""
    mock_chat = create_autospec(telegram.Chat, spec_set=True, instance=True)

    mock_chat.id = 123456789
    mock_chat.type = "group"

    raise NotImplementedError("This is a mock group chat, not implemented yet.")

    return mock_chat


@pytest.fixture
def mock_forum_chat():
    """Create a mock telegram.Chat object."""
    mock_chat = create_autospec(telegram.Chat, spec_set=True, instance=True)

    mock_chat.id = 123456789
    mock_chat.type = "forum"

    raise NotImplementedError("This is a mock forum chat, not implemented yet.")

    return mock_chat


@pytest.fixture
def mock_private_message(mock_private_chat):
    """Create a mock telegram.Message object."""
    mock_message = create_autospec(telegram.Message, spec_set=True, instance=True)

    mock_message.message_id = 1
    mock_message.text = "Hello, world!"

    # Create a proper mock user for from_user
    mock_from_user = create_autospec(telegram.User, spec_set=True, instance=True)
    mock_from_user.id = 987654321
    mock_from_user.first_name = "John"
    mock_from_user.username = "johndoe"

    mock_message.from_user = mock_from_user
    mock_message.chat = mock_private_chat
    mock_message.chat_id = mock_private_chat.id
    mock_message.date = DEFAULT_DATETIME

    return mock_message


@pytest.fixture
def mock_edited_private_message(mock_private_message):
    """Create a mock telegram.Message object for an edited message."""
    mock_private_message.edit_date = DEFAULT_DATETIME + timedelta(minutes=5)

    return mock_private_message


@pytest.fixture
def mock_update_empty():
    """Create a mock telegram.Update object."""
    mock_update = create_autospec(telegram.Update, spec_set=True, instance=True)

    mock_update.update_id = 1
    mock_update.message = None
    mock_update.edited_message = None
    mock_update.message_reaction = None
    mock_update.effective_user = None
    mock_update.effective_chat = None

    return mock_update


@pytest.fixture
def mock_update_private_chat_new_message(mock_update_empty, mock_private_message):
    """Create a mock telegram.Update object."""

    mock_update_empty.message = mock_private_message
    mock_update_empty.effective_user = mock_private_message.from_user
    mock_update_empty.effective_chat = mock_private_message.chat

    return mock_update_empty


@pytest.fixture
def mock_update_private_chat_edited_message(mock_update_empty, mock_edited_private_message):
    """Create a mock telegram.Update object."""

    mock_update_empty.edited_message = mock_edited_private_message
    mock_update_empty.effective_user = mock_edited_private_message.from_user
    mock_update_empty.effective_chat = mock_edited_private_message.chat

    return mock_update_empty


@pytest.fixture
def mock_reaction_type_emoji():
    """Create a mock ReactionTypeEmoji object."""
    mock_reaction = MagicMock()
    mock_reaction.type = "emoji"
    mock_reaction.emoji = "❤️"
    return mock_reaction


@pytest.fixture
def mock_message_reaction(mock_user, mock_private_chat, mock_reaction_type_emoji):
    """Create a mock telegram.MessageReactionUpdated object."""
    mock_reaction = create_autospec(telegram.MessageReactionUpdated, spec_set=True, instance=True)

    mock_reaction.chat = mock_private_chat
    mock_reaction.message_id = 123
    mock_reaction.user = mock_user
    mock_reaction.date = DEFAULT_DATETIME

    # Mock old and new reactions as tuples of ReactionType objects
    old_reaction_type = MagicMock()
    old_reaction_type.type = "emoji"
    old_reaction_type.emoji = "👍"

    mock_reaction.old_reaction = (old_reaction_type,)
    mock_reaction.new_reaction = (mock_reaction_type_emoji,)

    return mock_reaction


@pytest.fixture
def mock_update_message_reaction(mock_update_empty, mock_message_reaction):
    """Create a mock telegram.Update object with message reaction."""

    mock_update_empty.message_reaction = mock_message_reaction
    mock_update_empty.effective_user = mock_message_reaction.user
    mock_update_empty.effective_chat = mock_message_reaction.chat

    return mock_update_empty


@pytest.fixture
def mock_session():
    """Create a mock Sessions object."""

    mock_session = create_autospec(Sessions, spec_set=True, instance=True)
    mock_session.session_start = DEFAULT_DATETIME
    mock_session.last_user_message = DEFAULT_DATETIME
    mock_session.last_bot_message = None
    mock_session.last_user_activity = DEFAULT_DATETIME
    mock_session.last_bot_activity = None
    mock_session.session_end = None
    mock_session.message_count = None
    mock_session.new_message = AsyncMock()
    mock_session.new_activity = AsyncMock()
    mock_session.close_session = AsyncMock()
    mock_session.get_messages = AsyncMock()
    mock_session.has_bot_responded = False

    return mock_session


@pytest.fixture
def mock_voice():
    """Create a mock telegram.Voice object."""
    mock_voice = create_autospec(telegram.Voice, spec_set=True, instance=True)
    mock_voice.file_id = "voice_test_123"
    mock_voice.file_unique_id = "voice_unique_test_123"
    mock_voice.duration = 10
    mock_voice.mime_type = "audio/ogg"
    mock_voice.file_size = 1024

    # Mock get_file method
    mock_file = AsyncMock()
    mock_file.file_id = mock_voice.file_id
    mock_file.file_unique_id = mock_voice.file_unique_id
    mock_file.file_size = mock_voice.file_size
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"fake_voice_data"))

    mock_voice.get_file = AsyncMock(return_value=mock_file)

    return mock_voice


@pytest.fixture
def mock_photo():
    """Create a mock telegram.PhotoSize object."""
    mock_photo = create_autospec(telegram.PhotoSize, spec_set=True, instance=True)
    mock_photo.file_id = "photo_test_123"
    mock_photo.file_unique_id = "photo_unique_test_123"
    mock_photo.width = 1024
    mock_photo.height = 768
    mock_photo.file_size = 2048

    # Mock get_file method
    mock_file = AsyncMock()
    mock_file.file_id = mock_photo.file_id
    mock_file.file_unique_id = mock_photo.file_unique_id
    mock_file.file_size = mock_photo.file_size
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"fake_photo_data"))

    mock_photo.get_file = AsyncMock(return_value=mock_file)

    return mock_photo


@pytest.fixture
def mock_document():
    """Create a mock telegram.Document object."""
    mock_doc = create_autospec(telegram.Document, spec_set=True, instance=True)
    mock_doc.file_id = "doc_test_123"
    mock_doc.file_unique_id = "doc_unique_test_123"
    mock_doc.file_name = "test_document.pdf"
    mock_doc.mime_type = "application/pdf"
    mock_doc.file_size = 4096

    # Mock get_file method
    mock_file = AsyncMock()
    mock_file.file_id = mock_doc.file_id
    mock_file.file_unique_id = mock_doc.file_unique_id
    mock_file.file_size = mock_doc.file_size
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"fake_pdf_data"))

    mock_doc.get_file = AsyncMock(return_value=mock_file)

    return mock_doc


@pytest.fixture
def mock_video():
    """Create a mock telegram.Video object."""
    mock_video = create_autospec(telegram.Video, spec_set=True, instance=True)
    mock_video.file_id = "video_test_123"
    mock_video.file_unique_id = "video_unique_test_123"
    mock_video.width = 1920
    mock_video.height = 1080
    mock_video.duration = 60
    mock_video.mime_type = "video/mp4"
    mock_video.file_size = 8192

    # Mock get_file method
    mock_file = AsyncMock()
    mock_file.file_id = mock_video.file_id
    mock_file.file_unique_id = mock_video.file_unique_id
    mock_file.file_size = mock_video.file_size
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"fake_video_data"))

    mock_video.get_file = AsyncMock(return_value=mock_file)

    return mock_video


@pytest.fixture
def mock_message_with_voice(mock_private_chat, mock_voice):
    """Create a mock telegram.Message object with voice."""
    mock_message = create_autospec(telegram.Message, spec_set=True, instance=True)

    mock_message.message_id = 2
    mock_message.text = None
    mock_message.voice = mock_voice

    # Media attributes
    mock_message.photo = None
    mock_message.document = None
    mock_message.video = None
    mock_message.animation = None
    mock_message.sticker = None
    mock_message.video_note = None

    # Create a proper mock user for from_user
    mock_from_user = create_autospec(telegram.User, spec_set=True, instance=True)
    mock_from_user.id = 987654321
    mock_from_user.first_name = "John"
    mock_from_user.username = "johndoe"

    mock_message.from_user = mock_from_user
    mock_message.chat = mock_private_chat
    mock_message.chat_id = mock_private_chat.id
    mock_message.date = DEFAULT_DATETIME

    return mock_message


@pytest.fixture
def mock_message_with_photo(mock_private_chat, mock_photo):
    """Create a mock telegram.Message object with photo."""
    mock_message = create_autospec(telegram.Message, spec_set=True, instance=True)

    mock_message.message_id = 3
    mock_message.text = "Check out this photo!"
    mock_message.photo = [mock_photo]  # Photo is a list

    # Media attributes
    mock_message.voice = None
    mock_message.document = None
    mock_message.video = None
    mock_message.animation = None
    mock_message.sticker = None
    mock_message.video_note = None

    # Create a proper mock user for from_user
    mock_from_user = create_autospec(telegram.User, spec_set=True, instance=True)
    mock_from_user.id = 987654321
    mock_from_user.first_name = "John"
    mock_from_user.username = "johndoe"

    mock_message.from_user = mock_from_user
    mock_message.chat = mock_private_chat
    mock_message.chat_id = mock_private_chat.id
    mock_message.date = DEFAULT_DATETIME

    return mock_message


@pytest.fixture
def mock_message_with_document(mock_private_chat, mock_document):
    """Create a mock telegram.Message object with document."""
    mock_message = create_autospec(telegram.Message, spec_set=True, instance=True)

    mock_message.message_id = 4
    mock_message.text = "Here's the document"
    mock_message.document = mock_document

    # Media attributes
    mock_message.voice = None
    mock_message.photo = None
    mock_message.video = None
    mock_message.animation = None
    mock_message.sticker = None
    mock_message.video_note = None

    # Create a proper mock user for from_user
    mock_from_user = create_autospec(telegram.User, spec_set=True, instance=True)
    mock_from_user.id = 987654321
    mock_from_user.first_name = "John"
    mock_from_user.username = "johndoe"

    mock_message.from_user = mock_from_user
    mock_message.chat = mock_private_chat
    mock_message.chat_id = mock_private_chat.id
    mock_message.date = DEFAULT_DATETIME

    return mock_message
