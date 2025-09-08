"""Content encryption utilities using application-level key."""

from cryptography.fernet import Fernet

from areyouok_telegram.encryption.constants import APPLICATION_FERNET_KEY


def encrypt_content(value: str) -> str | None:
    """Encrypt content using the application-level key.

    Args:
        value: String value to encrypt

    Returns:
        str: The encrypted value as base64-encoded string, or None if value is None
    """
    if value is None:
        return None

    fernet = Fernet(APPLICATION_FERNET_KEY.encode())
    encrypted_bytes = fernet.encrypt(value.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_content(encrypted_value: str) -> str | None:
    """Decrypt content using the application-level key.

    Args:
        encrypted_value: Encrypted value to decrypt

    Returns:
        str: The decrypted value, or None if encrypted_value is None
    """
    if encrypted_value is None:
        return None

    fernet = Fernet(APPLICATION_FERNET_KEY.encode())
    encrypted_bytes = encrypted_value.encode("utf-8")
    decrypted_bytes = fernet.decrypt(encrypted_bytes)
    return decrypted_bytes.decode("utf-8")
