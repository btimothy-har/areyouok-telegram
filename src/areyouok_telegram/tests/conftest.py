"""Pytest configuration and shared fixtures for telegram bot testing."""

from datetime import UTC
from datetime import datetime
from unittest.mock import create_autospec

import pytest
import telegram

DEFAULT_DATETIME = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)


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
def mock_update_private_chat_new_message(mock_private_message):
    """Create a mock telegram.Update object."""
    mock_update = create_autospec(telegram.Update, spec_set=True, instance=True)

    mock_update.update_id = 1
    mock_update.message = mock_private_message
    mock_update.effective_user = mock_private_message.from_user
    mock_update.effective_chat = mock_private_message.chat

    return mock_update
