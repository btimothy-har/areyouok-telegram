import pydantic_ai


class InvalidMessageError(pydantic_ai.ModelRetry):
    """Exception raised when a message ID cannot be found."""

    def __init__(self, message_id: str):
        super().__init__(f"Message with ID {message_id} not found.")
        self.message_id = message_id


class ReactToSelfError(pydantic_ai.ModelRetry):
    """Exception raised when the agent tries to react to its own message."""

    def __init__(self, message_id: str):
        super().__init__(f"You cannot react to your own message {message_id}.")
        self.message_id = message_id


class UnacknowledgedImportantMessageError(pydantic_ai.ModelRetry):
    """Exception raised when an important message is not acknowledged."""

    def __init__(self, message: str):
        super().__init__(f"Important message not acknowledged: {message}")
        self.message = message
