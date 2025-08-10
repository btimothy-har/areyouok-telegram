"""Tests for user key encryption functionality."""

import base64
import hashlib

import pytest
from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

from areyouok_telegram.encryption.user_keys import decrypt_user_key
from areyouok_telegram.encryption.user_keys import encrypt_user_key
from areyouok_telegram.encryption.user_keys import generate_user_key


class TestUserKeys:
    """Test user key encryption functions."""

    def test_generate_user_key(self):
        """Test that generate_user_key creates a valid Fernet key."""
        key = generate_user_key()

        # Check it's a string
        assert isinstance(key, str)

        # Check it's a valid Fernet key by trying to create a Fernet instance
        fernet = Fernet(key.encode("utf-8"))
        assert fernet is not None

        # Test that keys are unique
        key2 = generate_user_key()
        assert key != key2

    def test_encrypt_user_key(self):
        """Test encrypting a user key with their username."""
        # Generate a test key
        test_key = generate_user_key()
        username = "testuser123"

        # Encrypt the key
        encrypted = encrypt_user_key(test_key, username)

        # Check it's a string
        assert isinstance(encrypted, str)

        # Check we can decrypt it with the same username
        username_hash = hashlib.sha256(username.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(username_hash)
        fernet = Fernet(fernet_key)

        # Decode the encrypted string back to bytes for decryption
        encrypted_bytes = base64.urlsafe_b64decode(encrypted.encode("utf-8"))
        decrypted = fernet.decrypt(encrypted_bytes)
        assert decrypted.decode("utf-8") == test_key

    def test_encrypt_user_key_different_usernames(self):
        """Test that different usernames produce different encrypted results."""
        test_key = generate_user_key()

        encrypted1 = encrypt_user_key(test_key, "user1")
        encrypted2 = encrypt_user_key(test_key, "user2")

        # Same key encrypted with different usernames should produce different results
        assert encrypted1 != encrypted2

    def test_encrypt_user_key_same_username(self):
        """Test that same username can decrypt the key."""
        test_key = generate_user_key()
        username = "consistent_user"

        # Encrypt multiple times with same username
        encrypted1 = encrypt_user_key(test_key, username)

        # Decrypt using the same username-derived key
        username_hash = hashlib.sha256(username.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(username_hash)
        fernet = Fernet(fernet_key)

        # Decode the encrypted string back to bytes for decryption
        encrypted_bytes = base64.urlsafe_b64decode(encrypted1.encode("utf-8"))
        decrypted = fernet.decrypt(encrypted_bytes)
        assert decrypted.decode("utf-8") == test_key

    def test_encrypt_user_key_wrong_username_fails(self):
        """Test that decrypting with wrong username fails."""
        test_key = generate_user_key()
        correct_username = "correct_user"
        wrong_username = "wrong_user"

        # Encrypt with correct username
        encrypted = encrypt_user_key(test_key, correct_username)

        # Try to decrypt with wrong username
        wrong_hash = hashlib.sha256(wrong_username.encode()).digest()
        wrong_fernet_key = base64.urlsafe_b64encode(wrong_hash)
        wrong_fernet = Fernet(wrong_fernet_key)

        # This should raise an exception
        with pytest.raises(InvalidToken):
            encrypted_bytes = base64.urlsafe_b64decode(encrypted.encode("utf-8"))
            wrong_fernet.decrypt(encrypted_bytes)

    def test_decrypt_user_key(self):
        """Test decrypting a user key with the correct username."""
        # Generate and encrypt a test key
        test_key = generate_user_key()
        username = "testuser"
        encrypted = encrypt_user_key(test_key, username)

        # Decrypt it
        decrypted = decrypt_user_key(encrypted, username)

        # Should match the original key
        assert decrypted == test_key

    def test_decrypt_user_key_wrong_username_fails(self):
        """Test that decrypt_user_key fails with wrong username."""
        test_key = generate_user_key()
        correct_username = "correct_user"
        wrong_username = "wrong_user"

        # Encrypt with correct username
        encrypted = encrypt_user_key(test_key, correct_username)

        # Try to decrypt with wrong username - should fail
        with pytest.raises(InvalidToken):
            decrypt_user_key(encrypted, wrong_username)
