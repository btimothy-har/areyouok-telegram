"""Exceptions for encryption-related operations."""


class ContentNotDecryptedError(Exception):
    """Raised when trying to access content that hasn't been decrypted yet."""

    def __init__(self, key: str):
        self.key = key
        super().__init__(f"Content for key '{key}' has not been decrypted yet. Call decrypt_content() first.")
