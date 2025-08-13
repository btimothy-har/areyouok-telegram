from datetime import UTC
from datetime import datetime

import logfire
from telegram.ext import ContextTypes

from areyouok_telegram.config import ENV
from areyouok_telegram.jobs import BaseJob
from areyouok_telegram.utils import telegram_retry


class PingJob(BaseJob):
    """
    Logs a "Ping" at the top of every hour to indicate bot is online and healthy.
    This is useful for monitoring services to track bot availability.
    """

    def __init__(self):
        """
        Initialize the ping job.
        """
        super().__init__()
        self._startup_time = datetime.now(UTC)

    @property
    def name(self) -> str:
        return "ping_status"

    @telegram_retry()
    async def _run(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Log a ping with bot status information.
        """
        bot_info = await context.bot.get_me()
        current_time = datetime.now(UTC)
        uptime = current_time - self._startup_time

        logfire.info(
            "Ping",
            bot_id=bot_info.id,
            bot_username=bot_info.username,
            bot_name=bot_info.first_name,
            environment=ENV,
            timestamp=current_time.isoformat(),
            uptime_seconds=uptime.total_seconds(),
            uptime_formatted=str(uptime),
            job_queue_size=len(context.job_queue.jobs()),
        )
