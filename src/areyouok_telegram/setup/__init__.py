"""Setup package for application initialization."""

from areyouok_telegram.setup.bot import (
    package_version,
    setup_bot_commands,
    setup_bot_description,
    setup_bot_name,
    setup_bot_short_description,
)
from areyouok_telegram.setup.database import create_bot_user, database_setup
from areyouok_telegram.setup.jobs import (
    restore_active_sessions,
    start_context_embedding_job,
    start_data_warning_job,
    start_ping_job,
    start_profile_generation_job,
)

__all__ = [
    "database_setup",
    "create_bot_user",
    "package_version",
    "setup_bot_name",
    "setup_bot_description",
    "setup_bot_short_description",
    "restore_active_sessions",
    "setup_bot_commands",
    "start_data_warning_job",
    "start_ping_job",
    "start_context_embedding_job",
    "start_profile_generation_job",
]
