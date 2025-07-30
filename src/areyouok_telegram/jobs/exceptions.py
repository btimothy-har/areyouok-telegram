class BaseConversationJobError(Exception):
    """Base exception for all conversation job-related errors."""

    pass


class NoActiveSessionError(BaseConversationJobError):
    """Raised when there is no active chat session for the conversation job."""

    def __init__(self, chat_id: str):
        super().__init__(f"No active chat session found for chat ID: {chat_id}")
        self.chat_id = chat_id
