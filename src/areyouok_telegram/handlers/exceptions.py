class BaseHandlerError(Exception):
    """Base class for all handler-related exceptions."""


class NoMessageError(BaseHandlerError):
    """Raised when a message is expected but not found."""

    def __init__(self, update_id):
        super().__init__(f"Expected to receive a new message in update: {update_id}")
        self.update_id = update_id


class NoEditedMessageError(BaseHandlerError):
    """Raised when an edited message is expected but not found."""

    def __init__(self, update_id):
        super().__init__(f"Expected to receive an edited message in update: {update_id}")
        self.update_id = update_id
