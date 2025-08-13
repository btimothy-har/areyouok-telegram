"""Exceptions for encryption-related operations."""


class ContentNotDecryptedError(Exception):
    """Raised when trying to access content that hasn't been decrypted yet."""

    def __init__(self, field_name: str):
        self.field_name = field_name
        super().__init__(f"Content for field '{field_name}' has not been decrypted yet. Call decrypt_content() first.")
