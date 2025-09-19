import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.logging import traced
from areyouok_telegram.utils import db_retry


@traced(extract_args=["update"])
@db_retry()
async def on_feedback_command(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /feedback command - provide a feedback URL to the user."""
    return
