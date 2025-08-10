import base64
import hashlib

from cryptography.fernet import Fernet


def generate_user_key() -> str:
    """Generate a new Fernet encryption key for a user.

    Returns:
        str: A new Fernet key as base64-encoded string
    """
    return Fernet.generate_key().decode("utf-8")


def encrypt_user_key(key: str, username: str) -> str:
    """Encrypt a user's key using their username as the encryption key.

    Args:
        key: The Fernet key to encrypt (base64-encoded string)
        username: The username to use as the encryption key

    Returns:
        str: The encrypted key as base64-encoded string
    """
    # Derive a Fernet-compatible key from the username
    # Fernet requires a 32-byte key encoded as base64
    username_hash = hashlib.sha256(username.encode()).digest()
    # Fernet needs base64-encoded 32-byte key
    fernet_key = base64.urlsafe_b64encode(username_hash)

    # Create Fernet instance with the derived key
    fernet = Fernet(fernet_key)

    # Encrypt the user's key (convert to bytes first)
    encrypted_key = fernet.encrypt(key.encode("utf-8"))

    # Return as base64-encoded string
    return base64.urlsafe_b64encode(encrypted_key).decode("utf-8")


def decrypt_user_key(encrypted_key: str, username: str) -> str:
    """Decrypt a user's key using their username as the decryption key.

    Args:
        encrypted_key: The encrypted key as base64-encoded string
        username: The username to use as the decryption key

    Returns:
        str: The decrypted Fernet key as base64-encoded string

    Raises:
        InvalidToken: If the key cannot be decrypted (wrong username or corrupted data)
    """
    # Derive a Fernet-compatible key from the username
    username_hash = hashlib.sha256(username.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(username_hash)

    # Create Fernet instance with the derived key
    fernet = Fernet(fernet_key)

    # Decode the encrypted string back to bytes for decryption
    encrypted_bytes = base64.urlsafe_b64decode(encrypted_key.encode("utf-8"))

    # Decrypt and return as string
    decrypted = fernet.decrypt(encrypted_bytes)
    return decrypted.decode("utf-8")
