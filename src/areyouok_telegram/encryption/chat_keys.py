import base64
import hashlib

from cryptography.fernet import Fernet

from areyouok_telegram.config import USER_ENCRYPTION_SALT


def generate_chat_key() -> str:
    """Generate a new Fernet encryption key for a chat.

    Returns:
        str: A new Fernet key as base64-encoded string
    """
    return Fernet.generate_key().decode("utf-8")


def encrypt_chat_key(key: str) -> str:
    """Encrypt a chat's key using the application salt.

    Args:
        key: The Fernet key to encrypt (base64-encoded string)

    Returns:
        str: The encrypted key as base64-encoded string
    """
    # Derive a Fernet-compatible key from the application salt
    # Fernet requires a 32-byte key encoded as base64
    salt_hash = hashlib.sha256(USER_ENCRYPTION_SALT.encode()).digest()
    # Fernet needs base64-encoded 32-byte key
    fernet_key = base64.urlsafe_b64encode(salt_hash)

    # Create Fernet instance with the derived key
    fernet = Fernet(fernet_key)

    # Encrypt the chat's key (convert to bytes first)
    encrypted_key = fernet.encrypt(key.encode("utf-8"))

    # Return as base64-encoded string
    return base64.urlsafe_b64encode(encrypted_key).decode("utf-8")


def decrypt_chat_key(encrypted_key: str) -> str:
    """Decrypt a chat's key using the application salt.

    Args:
        encrypted_key: The encrypted key as base64-encoded string

    Returns:
        str: The decrypted Fernet key as base64-encoded string

    Raises:
        InvalidToken: If the key cannot be decrypted (corrupted data)
    """
    # Derive a Fernet-compatible key from the application salt
    salt_hash = hashlib.sha256(USER_ENCRYPTION_SALT.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(salt_hash)

    # Create Fernet instance with the derived key
    fernet = Fernet(fernet_key)

    # Decode the encrypted string back to bytes for decryption
    encrypted_bytes = base64.urlsafe_b64decode(encrypted_key.encode("utf-8"))

    # Decrypt and return as string
    decrypted = fernet.decrypt(encrypted_bytes)
    return decrypted.decode("utf-8")
