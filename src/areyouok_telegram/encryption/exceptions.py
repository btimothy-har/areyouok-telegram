class BaseEncryptionError(Exception):
    """Base class for all encryption-related errors."""

    pass


class ProfileNotDecryptedError(BaseEncryptionError):
    """Raised when a profile is not decrypted."""

    def __init__(self, user_id: str):
        super().__init__(f"Profile for user_id {user_id} is not decrypted.")
        self.user_id = user_id


class ContentNotDecryptedError(BaseEncryptionError):
    """Raised when content cannot be decrypted."""

    def __init__(self, file_key: str):
        super().__init__(f"Content for file_key {file_key} is not decrypted.")
        self.file_key = file_key
