"""Exceptions for encryption-related operations."""


class ContentNotDecryptedError(Exception):
    """Raised when trying to access content that hasn't been decrypted yet."""

    def __init__(self, key: str):
        self.key = key
        super().__init__(f"Content for key '{key}' has not been decrypted yet. Call decrypt_content() first.")


class ProfileNotDecryptedError(Exception):
    """Raised when trying to access a user's encryption key without providing username."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        super().__init__(f"User profile for user_id '{user_id}' has not been decrypted. Provide username to decrypt.")
