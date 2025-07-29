"""Bot metadata and configuration."""

import logging
from importlib.metadata import version

import telegram
from telegram.ext import Application
from telegram.ext import ContextTypes

from areyouok_telegram.config import ENV
from areyouok_telegram.setup.exceptions import BotDescriptionSetupError
from areyouok_telegram.setup.exceptions import BotNameSetupError

logger = logging.getLogger(__name__)


def package_version():
    """Get the package version."""
    return version("areyouok-telegram")


def _generate_bot_name():
    """Generate environment-specific bot name."""
    if ENV == "production":
        return "Are You OK?"
    return f"Are You OK? [{ENV}]"


def _generate_short_description():
    """Generate a short description for the bot."""
    description = (
        f"Your empathic companion for everyday life. Here to listen, support & help 24/7."
        f"\n\n[{ENV} v{version('areyouok-telegram')}]"
    )
    return description


async def setup_bot_name(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Set the bot name with proper error handling."""
    name = _generate_bot_name()

    try:
        success = await ctx.bot.set_my_name(name=name)
    except telegram.error.RetryAfter as e:
        logging.warning(f"Rate limit exceeded while setting bot name, retrying after {e.retry_after} seconds.")

        # Retry after the specified time
        ctx.job_queue.run_once(
            callback=setup_bot_name,
            when=e.retry_after + 60,
            name="retry_set_bot_name",
        )
        return

    if not success:
        raise BotNameSetupError(name)

    logging.debug(f"Bot name set to: {name}")


async def setup_bot_description(ctx: Application | ContextTypes.DEFAULT_TYPE):
    """Set the bot description with proper error handling."""
    description = _generate_short_description()

    try:
        # Attempt to set the bot description
        success = await ctx.bot.set_my_description(description=description)
    except telegram.error.RetryAfter as e:
        logging.warning(f"Rate limit exceeded while setting bot description, retrying after {e.retry_after} seconds.")

        # Retry after the specified time
        ctx.job_queue.run_once(
            callback=setup_bot_description,
            when=e.retry_after + 60,
            name="retry_set_bot_description",
        )
        return

    success = await ctx.bot.set_my_short_description(short_description=description)

    if not success:
        raise BotDescriptionSetupError()

    logging.debug(f"Bot description set to: {description}")
