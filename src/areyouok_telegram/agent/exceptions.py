class BaseResponseError(Exception):
    """Base class for all response errors."""

    pass


class InvalidMessageError(BaseResponseError):
    """Exception raised when a message ID cannot be found."""

    def __init__(self, message_id: str):
        super().__init__(f"Message with ID {message_id} not found.")
        self.message_id = message_id


class ReactToSelfError(BaseResponseError):
    """Exception raised when the agent tries to react to its own message."""

    def __init__(self, message_id: str):
        super().__init__(f"You cannot react to your own message {message_id}.")
        self.message_id = message_id
