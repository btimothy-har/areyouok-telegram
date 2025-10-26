class BaseDataError(Exception):
    """Base class for all data-related exceptions."""


class InvalidIDArgumentError(ValueError, BaseDataError):
    """Raised when an ID argument is invalid or improperly formatted."""

    def __init__(self, id_arguments: list[str]):
        super().__init__(f"Provide exactly one of: {', '.join(id_arguments)}")
        self.id_arguments = id_arguments


class MissingEncryptionKeyError(ValueError, BaseDataError):
    """Raised when a saved Chat instance is missing its encryption key."""

    def __init__(self, chat_id: int):
        super().__init__(f"Chat with id {chat_id} must have an encrypted_key")
        self.chat_id = chat_id
