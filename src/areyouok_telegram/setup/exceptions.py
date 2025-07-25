"""Custom exceptions for setup operations."""


class BotSetupError(Exception):
    """Base exception for bot setup operations."""


class BotNameSetupError(BotSetupError):
    """Raised when bot name configuration fails."""

    def __init__(self, bot_name: str):
        super().__init__(f"Failed to set bot name to '{bot_name}'. Please check your bot token and permissions.")


class BotDescriptionSetupError(BotSetupError):
    """Raised when bot description configuration fails."""

    def __init__(self):
        super().__init__("Failed to set bot description. Please check your bot token and permissions.")
