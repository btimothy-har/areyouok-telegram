"""Bot metadata and configuration."""

import logging
from importlib.metadata import version

from telegram.ext import Application

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


async def setup_bot_name(application: Application):
    """Set the bot name with proper error handling."""
    name = _generate_bot_name()
    success = await application.bot.set_my_name(name=name)

    if not success:
        raise BotNameSetupError(name)

    logging.debug(f"Bot name set to: {name}")


async def setup_bot_description(application: Application):
    """Set the bot description with proper error handling."""
    description = _generate_short_description()
    success = await application.bot.set_my_short_description(short_description=description)

    if not success:
        raise BotDescriptionSetupError()

    logging.debug(f"Bot description set to: {description}")
