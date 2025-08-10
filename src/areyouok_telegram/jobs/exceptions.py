"""Exceptions for job processing."""


class UserNotFoundForChatError(Exception):
    """Raised when no user is found for a given chat_id.

    This typically indicates the job is running for a non-private chat,
    where chat_id does not correspond to a user_id.
    """

    def __init__(self, chat_id: str):
        """Initialize the exception with the chat_id that caused the error."""
        super().__init__(f"No user found for chat_id {chat_id}. This appears to be a non-private chat.")
        self.chat_id = chat_id
