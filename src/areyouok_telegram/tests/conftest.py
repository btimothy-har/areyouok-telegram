"""Pytest configuration and shared fixtures for telegram bot testing."""

from unittest.mock import Mock

import pytest
import telegram


@pytest.fixture
def mock_user():
    """Create a mock telegram.User object."""
    mock_user = Mock(spec=telegram.User)

    mock_user.id = 987654321
    mock_user.first_name = "John"
    mock_user.last_name = "Doe"
    mock_user.username = "johndoe"
    mock_user.is_bot = False
    mock_user.language_code = "en"

    return mock_user
