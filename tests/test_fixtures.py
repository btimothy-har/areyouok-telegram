from datetime import UTC
from datetime import datetime
from datetime import timedelta

import telegram
from freezegun import freeze_time
from telegram.constants import ChatType


def test_user_fixture(mock_user):
    """Test that test_user fixture returns a proper Mock."""
    # Check it's a Mock with telegram.User spec
    assert hasattr(mock_user, "_spec_class")
    assert mock_user._spec_class == telegram.User

    assert mock_user.id == 987654321
    assert mock_user.first_name == "John"
    assert mock_user.username == "johndoe"
    assert mock_user.is_bot is False

    # Test Telegram User properties
    assert mock_user.full_name == "John Doe"
    assert mock_user.link == "https://t.me/johndoe"


def test_private_chat_fixture(mock_private_chat):
    """Test that test_private_chat fixture returns a proper Mock."""
    # Check it's a Mock with telegram.Chat spec
    assert hasattr(mock_private_chat, "_spec_class")
    assert mock_private_chat._spec_class == telegram.Chat

    assert mock_private_chat.id == 123456789
    assert mock_private_chat.type == ChatType.PRIVATE
    assert mock_private_chat.username == "johndoe"
    assert mock_private_chat.first_name == "John"
    assert mock_private_chat.last_name == "Doe"

    # Mock methods can be called and return values
    assert mock_private_chat.full_name == "John Doe"
    assert mock_private_chat.link == "https://t.me/johndoe"


@freeze_time("2025-01-01 12:00:00", tz_offset=0)
def test_private_message_fixture(mock_private_message):
    """Test that test_private_message fixture returns a proper Mock."""
    # Check it's a Mock with telegram.Message spec
    assert hasattr(mock_private_message, "_spec_class")
    assert mock_private_message._spec_class == telegram.Message

    assert mock_private_message.text == "Hello, world!"
    assert mock_private_message.message_id == 1
    assert mock_private_message.from_user.id == 987654321
    assert mock_private_message.chat.id == mock_private_message.chat_id == 123456789

    assert mock_private_message.date == datetime.now(tz=UTC)


@freeze_time("2025-01-01 12:00:00", tz_offset=0)
def test_edited_private_message_fixture(mock_edited_private_message):
    """Test that test_edited_private_message fixture returns a proper Mock."""
    # Check it's a Mock with telegram.Message spec
    assert hasattr(mock_edited_private_message, "_spec_class")
    assert mock_edited_private_message._spec_class == telegram.Message

    assert mock_edited_private_message.text == "Hello, world!"
    assert mock_edited_private_message.message_id == 1
    assert mock_edited_private_message.from_user.id == 987654321
    assert mock_edited_private_message.chat.id == mock_edited_private_message.chat_id == 123456789

    assert mock_edited_private_message.date == datetime.now(tz=UTC)
    assert mock_edited_private_message.edit_date == datetime.now(tz=UTC) + timedelta(minutes=5)


def test_update_empty(mock_update_empty):
    """Test that test_update_empty fixture returns a proper Mock."""
    # Check it's a Mock with telegram.Update spec
    assert hasattr(mock_update_empty, "_spec_class")
    assert mock_update_empty._spec_class == telegram.Update

    assert mock_update_empty.update_id == 1
    assert mock_update_empty.message is None
    assert mock_update_empty.edited_message is None
    assert mock_update_empty.effective_user is None
    assert mock_update_empty.effective_chat is None


def test_update_new_message_from_private_chat(mock_update_private_chat_new_message):
    """Test that test_update_new_message_from_private_chat fixture returns a proper Mock."""
    # Check it's a Mock with telegram.Update spec
    assert hasattr(mock_update_private_chat_new_message, "_spec_class")
    assert mock_update_private_chat_new_message._spec_class == telegram.Update

    assert mock_update_private_chat_new_message.update_id == 1
    assert mock_update_private_chat_new_message.message.message_id == 1
    assert (
        mock_update_private_chat_new_message.effective_user.id
        == mock_update_private_chat_new_message.message.from_user.id
    )
    assert (
        mock_update_private_chat_new_message.effective_chat.id == mock_update_private_chat_new_message.message.chat.id
    )
