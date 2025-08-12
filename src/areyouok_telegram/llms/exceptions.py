import pydantic_ai


class BaseModelError(Exception):
    """Base class for all model-related exceptions."""


class ModelInputError(BaseModelError):
    """Exception raised for errors in model input."""

    def __init__(self):
        message = "Either model_id or openrouter_id must be provided."
        super().__init__(message)


class ModelConfigurationError(BaseModelError):
    """Exception raised for errors in model configuration."""

    def __init__(self):
        message = "No valid model configuration found. Ensure either primary or OpenRouter model is set."
        super().__init__(message)


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

    def __init__(self, message: str, feedback: str = ""):
        super().__init__(f"Important message not acknowledged: {message}. {feedback}")
        self.message = message
        self.feedback = feedback
