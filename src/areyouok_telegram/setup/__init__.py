"""Setup package for application initialization."""

from areyouok_telegram.setup.bot import package_version
from areyouok_telegram.setup.bot import setup_bot_commands
from areyouok_telegram.setup.bot import setup_bot_description
from areyouok_telegram.setup.bot import setup_bot_name
from areyouok_telegram.setup.database import database_setup
from areyouok_telegram.setup.jobs import restore_active_sessions
from areyouok_telegram.setup.jobs import start_data_warning_job

__all__ = [
    "database_setup",
    "package_version",
    "setup_bot_name",
    "setup_bot_description",
    "restore_active_sessions",
    "setup_bot_commands",
    "start_data_warning_job",
]
