from unittest.mock import Mock

import telegram


def test_user_fixture(mock_user):
    """Test that test_user fixture returns a proper Mock."""
    # Check it's a Mock with telegram.User spec
    assert isinstance(mock_user, Mock)
    assert mock_user._spec_class == telegram.User

    assert mock_user.id == 987654321
    assert mock_user.first_name == "John"
    assert mock_user.username == "johndoe"
    assert mock_user.is_bot is False

    print(f"Mock user created successfully: {mock_user}")
    print(f"User ID: {mock_user.id}")
    print(f"User name: {mock_user.first_name}")


def test_user_fixture_telegram_methods(mock_user):
    """Test using the mock as if it were a real telegram.User."""
    # Set up the mock with realistic telegram user data

    user_id = mock_user.id
    name = mock_user.first_name

    assert user_id == 987654321
    assert name == "John"

    # Mock methods can be called and return values
    mock_user.mention_markdown.return_value = "[John](tg://user?id=987654321)"
    mention = mock_user.mention_markdown()
    assert mention == "[John](tg://user?id=987654321)"

    print(f"Successfully used mock as telegram.User: {name} (ID: {user_id})")
