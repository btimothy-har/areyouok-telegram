import logfire

from areyouok_telegram.config import CONTROLLED_ENV
from areyouok_telegram.config import ENV
from areyouok_telegram.config import LOG_CHAT_MESSAGES
from areyouok_telegram.config import USER_ENCRYPTION_SALT
from areyouok_telegram.jobs import BaseJob


class DataLogWarningJob(BaseJob):
    """
    Publishes a warning to logs when chat messages are being logged in a controlled environment.
    """

    def __init__(self):
        """
        Initialize the data log warning job.
        """
        super().__init__()

    @property
    def name(self) -> str:
        return "data_log_warning"

    async def run_job(self) -> None:
        if LOG_CHAT_MESSAGES and ENV in CONTROLLED_ENV:
            logfire.warning(
                "Logging chat messages in a controlled environment. "
                "This may expose sensitive user data. Ensure this is intentional."
            )

        if USER_ENCRYPTION_SALT == "default-salt" and ENV in CONTROLLED_ENV:
            logfire.warning(
                "USER_ENCRYPTION_SALT is set to the default value. "
                "This should be changed in production to ensure user data security."
            )
