import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import environment_override
from areyouok_telegram.utils import traced


@traced(extract_args=["update"])
@db_retry()
@environment_override({
    "research": "on_start_command_research",
})
async def on_start_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    return


@traced(extract_args=["update"])
@db_retry()
@environment_override({
    "research": "on_end_command_research",
})
async def on_end_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: ARG001
    return
