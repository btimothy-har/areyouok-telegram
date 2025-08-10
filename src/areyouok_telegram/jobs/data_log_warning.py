import logfire
from telegram.ext import ContextTypes

from areyouok_telegram.config import CONTROLLED_ENV
from areyouok_telegram.config import ENV
from areyouok_telegram.config import LOG_CHAT_MESSAGES
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

    async def _run(self, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        if LOG_CHAT_MESSAGES and ENV in CONTROLLED_ENV:
            logfire.warning(
                "Logging chat messages is enabled in a controlled environment. "
                "This may expose sensitive user data. Ensure this is intentional."
            )
