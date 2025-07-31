"""Setup package for application initialization."""

from areyouok_telegram.setup.bot import package_version
from areyouok_telegram.setup.bot import setup_bot_description
from areyouok_telegram.setup.bot import setup_bot_name
from areyouok_telegram.setup.conversations import setup_conversation_runners
from areyouok_telegram.setup.database import database_setup
from areyouok_telegram.setup.logging import logging_setup

__all__ = [
    "database_setup",
    "logging_setup",
    "package_version",
    "setup_bot_name",
    "setup_bot_description",
    "setup_conversation_runners",
]
