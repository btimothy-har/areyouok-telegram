class BaseHandlerError(Exception):
    """Base class for all handler-related exceptions."""


class NoMessageError(BaseHandlerError):
    """Raised when a message is expected but not found."""

    def __init__(self, update_id):
        super().__init__(f"Expected to receive a new message in update: {update_id}")
        self.update_id = update_id


class NoChatFoundError(BaseHandlerError):
    """Raised when a chat is expected but not found."""

    def __init__(self, chat_id):
        super().__init__(f"Chat not found for chat_id: {chat_id}")
        self.chat_id = chat_id


class NoUserFoundError(BaseHandlerError):
    """Raised when a user is expected but not found."""

    def __init__(self, user_id):
        super().__init__(f"User not found for user_id: {user_id}")
        self.user_id = user_id


class NoEditedMessageError(BaseHandlerError):
    """Raised when an edited message is expected but not found."""

    def __init__(self, update_id):
        super().__init__(f"Expected to receive an edited message in update: {update_id}")
        self.update_id = update_id


class NoMessageReactionError(BaseHandlerError):
    """Raised when a message reaction is expected but not found."""

    def __init__(self, update_id):
        super().__init__(f"Expected to receive a message reaction in update: {update_id}")
        self.update_id = update_id


class InvalidCallbackDataError(BaseHandlerError):
    """Raised when callback data is invalid or improperly formatted."""

    def __init__(self, update_id):
        super().__init__(f"Invalid callback data in update: {update_id}")
        self.update_id = update_id
