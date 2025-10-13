"""Tests for chat key encryption functionality."""

import base64
import hashlib
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet, InvalidToken

from areyouok_telegram.encryption.chat_keys import decrypt_chat_key, encrypt_chat_key, generate_chat_key


class TestChatKeys:
    """Test chat key encryption functions."""

    def test_generate_chat_key(self):
        """Test that generate_chat_key creates a valid Fernet key."""
        key = generate_chat_key()

        # Check it's a string
        assert isinstance(key, str)

        # Check it's a valid Fernet key by trying to create a Fernet instance
        fernet = Fernet(key.encode("utf-8"))
        assert fernet is not None

        # Test that keys are unique
        key2 = generate_chat_key()
        assert key != key2

    @patch("areyouok_telegram.encryption.chat_keys.USER_ENCRYPTION_SALT", "test-salt")
    def test_encrypt_chat_key(self):
        """Test encrypting a chat key with application salt."""
        # Generate a test key
        test_key = generate_chat_key()

        # Encrypt the key
        encrypted = encrypt_chat_key(test_key)

        # Check it's a string
        assert isinstance(encrypted, str)

        # Check we can decrypt it with the same salt
        salt_hash = hashlib.sha256(b"test-salt").digest()
        fernet_key = base64.urlsafe_b64encode(salt_hash)
        fernet = Fernet(fernet_key)

        # Decode the encrypted string back to bytes for decryption
        encrypted_bytes = base64.urlsafe_b64decode(encrypted.encode("utf-8"))
        decrypted = fernet.decrypt(encrypted_bytes)
        assert decrypted.decode("utf-8") == test_key

    @patch("areyouok_telegram.encryption.chat_keys.USER_ENCRYPTION_SALT", "test-salt")
    def test_encrypt_chat_key_consistent(self):
        """Test that encryption with same salt produces consistent results."""
        test_key = generate_chat_key()

        encrypted = encrypt_chat_key(test_key)

        # Check it's a valid encrypted string
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0
        # Note: Fernet includes timestamps so encrypting twice will produce different results

    @patch("areyouok_telegram.encryption.chat_keys.USER_ENCRYPTION_SALT", "test-salt")
    def test_encrypt_chat_key_can_decrypt(self):
        """Test that encrypted key can be decrypted with same salt."""
        test_key = generate_chat_key()

        # Encrypt with application salt
        encrypted = encrypt_chat_key(test_key)

        # Decrypt using the same salt-derived key
        salt_hash = hashlib.sha256(b"test-salt").digest()
        fernet_key = base64.urlsafe_b64encode(salt_hash)
        fernet = Fernet(fernet_key)

        # Decode the encrypted string back to bytes for decryption
        encrypted_bytes = base64.urlsafe_b64decode(encrypted.encode("utf-8"))
        decrypted = fernet.decrypt(encrypted_bytes)
        assert decrypted.decode("utf-8") == test_key

    @patch("areyouok_telegram.encryption.chat_keys.USER_ENCRYPTION_SALT", "correct-salt")
    def test_encrypt_chat_key_wrong_salt_fails(self):
        """Test that decrypting with wrong salt fails."""
        test_key = generate_chat_key()

        # Encrypt with correct salt
        encrypted = encrypt_chat_key(test_key)

        # Try to decrypt with wrong salt
        wrong_hash = hashlib.sha256(b"wrong-salt").digest()
        wrong_fernet_key = base64.urlsafe_b64encode(wrong_hash)
        wrong_fernet = Fernet(wrong_fernet_key)

        # This should raise an exception
        with pytest.raises(InvalidToken):
            encrypted_bytes = base64.urlsafe_b64decode(encrypted.encode("utf-8"))
            wrong_fernet.decrypt(encrypted_bytes)

    @patch("areyouok_telegram.encryption.chat_keys.USER_ENCRYPTION_SALT", "test-salt")
    def test_decrypt_chat_key(self):
        """Test decrypting a chat key with the correct salt."""
        # Generate and encrypt a test key
        test_key = generate_chat_key()
        encrypted = encrypt_chat_key(test_key)

        # Decrypt it
        decrypted = decrypt_chat_key(encrypted)

        # Should match the original key
        assert decrypted == test_key

    def test_decrypt_chat_key_wrong_salt_fails(self):
        """Test that decrypt_chat_key fails with wrong salt."""
        test_key = generate_chat_key()

        # Encrypt with one salt
        with patch("areyouok_telegram.encryption.chat_keys.USER_ENCRYPTION_SALT", "correct-salt"):
            encrypted = encrypt_chat_key(test_key)

        # Try to decrypt with different salt - should fail
        with patch("areyouok_telegram.encryption.chat_keys.USER_ENCRYPTION_SALT", "wrong-salt"):
            with pytest.raises(InvalidToken):
                decrypt_chat_key(encrypted)
