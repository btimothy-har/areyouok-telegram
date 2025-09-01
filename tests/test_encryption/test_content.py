"""Tests for content encryption utilities."""

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

from areyouok_telegram.encryption.content import decrypt_content
from areyouok_telegram.encryption.content import encrypt_content


class TestEncryptContent:
    """Test encrypt_content function."""

    def test_encrypt_content_with_string(self):
        """Test encrypt_content encrypts string values correctly."""
        test_value = "test_string"

        result = encrypt_content(test_value)

        # Result should not be None and should be different from input
        assert result is not None
        assert result != test_value
        assert isinstance(result, str)

    def test_encrypt_content_with_none(self):
        """Test encrypt_content returns None for None input."""
        result = encrypt_content(None)

        assert result is None

    def test_encrypt_content_with_empty_string(self):
        """Test encrypt_content handles empty string."""
        test_value = ""

        result = encrypt_content(test_value)

        assert result is not None
        assert result != test_value
        assert isinstance(result, str)

    def test_encrypt_content_with_unicode(self):
        """Test encrypt_content handles unicode characters."""
        test_value = "Test with émojis 🚀 and ñoñó"

        result = encrypt_content(test_value)

        assert result is not None
        assert result != test_value
        assert isinstance(result, str)

    def test_encrypt_content_consistency(self):
        """Test encrypt_content produces different results for same input (proper randomness)."""
        test_value = "consistent_test"

        result1 = encrypt_content(test_value)
        result2 = encrypt_content(test_value)

        # Results should be different due to Fernet's built-in randomness
        assert result1 != result2
        assert result1 is not None
        assert result2 is not None

    @patch("areyouok_telegram.encryption.content.APPLICATION_FERNET_KEY")
    def test_encrypt_content_uses_application_key(self, mock_key):
        """Test encrypt_content uses APPLICATION_FERNET_KEY."""
        mock_key.encode.return_value = Fernet.generate_key()
        test_value = "test"

        encrypt_content(test_value)

        # Verify the key was accessed and encoded
        mock_key.encode.assert_called_once()

    @patch("areyouok_telegram.encryption.content.Fernet")
    def test_encrypt_content_fernet_usage(self, mock_fernet_class):
        """Test encrypt_content creates Fernet instance and calls encrypt correctly."""
        mock_fernet = mock_fernet_class.return_value
        mock_fernet.encrypt.return_value = b"encrypted_bytes"
        test_value = "test"

        result = encrypt_content(test_value)

        # Verify Fernet was instantiated and encrypt was called
        mock_fernet_class.assert_called_once()
        mock_fernet.encrypt.assert_called_once_with(test_value.encode("utf-8"))
        assert result == "encrypted_bytes"


class TestDecryptContent:
    """Test decrypt_content function."""

    def test_decrypt_content_with_none(self):
        """Test decrypt_content returns None for None input."""
        result = decrypt_content(None)

        assert result is None

    def test_decrypt_content_with_valid_encrypted_value(self):
        """Test decrypt_content decrypts valid encrypted value."""
        # First encrypt a value to get a valid encrypted string
        original_value = "test_decryption"
        encrypted_value = encrypt_content(original_value)

        result = decrypt_content(encrypted_value)

        assert result == original_value

    def test_decrypt_content_with_empty_string_value(self):
        """Test decrypt_content handles empty string encryption/decryption."""
        # First encrypt empty string
        original_value = ""
        encrypted_value = encrypt_content(original_value)

        result = decrypt_content(encrypted_value)

        assert result == original_value

    def test_decrypt_content_with_unicode_value(self):
        """Test decrypt_content handles unicode characters."""
        # First encrypt unicode string
        original_value = "Tëst wíth üñíçödé 🌟"
        encrypted_value = encrypt_content(original_value)

        result = decrypt_content(encrypted_value)

        assert result == original_value

    def test_decrypt_content_with_invalid_encrypted_value(self):
        """Test decrypt_content raises error for invalid encrypted value."""
        invalid_encrypted_value = "not_a_valid_encrypted_string"

        with pytest.raises(InvalidToken):  # Fernet will raise InvalidToken
            decrypt_content(invalid_encrypted_value)

    def test_decrypt_content_with_malformed_base64(self):
        """Test decrypt_content handles malformed base64."""
        malformed_encrypted_value = "invalid!!base64!!"

        with pytest.raises((InvalidToken, ValueError)):  # Could raise either exception
            decrypt_content(malformed_encrypted_value)

    @patch("areyouok_telegram.encryption.content.APPLICATION_FERNET_KEY")
    def test_decrypt_content_uses_application_key(self, mock_key):
        """Test decrypt_content uses APPLICATION_FERNET_KEY."""
        mock_key.encode.return_value = Fernet.generate_key()

        # Create a valid encrypted value first
        test_value = "test"
        encrypted_value = encrypt_content(test_value)

        # Reset mock call count from encrypt_content
        mock_key.encode.reset_mock()

        decrypt_content(encrypted_value)

        # Verify the key was accessed and encoded for decrypt
        mock_key.encode.assert_called_once()

    @patch("areyouok_telegram.encryption.content.Fernet")
    def test_decrypt_content_fernet_usage(self, mock_fernet_class):
        """Test decrypt_content creates Fernet instance and calls decrypt correctly."""
        mock_fernet = mock_fernet_class.return_value
        mock_fernet.decrypt.return_value = b"decrypted_bytes"
        encrypted_value = "test_encrypted_value"

        result = decrypt_content(encrypted_value)

        # Verify Fernet was instantiated and decrypt was called
        mock_fernet_class.assert_called_once()
        mock_fernet.decrypt.assert_called_once_with(encrypted_value.encode("utf-8"))
        assert result == "decrypted_bytes"


class TestEncryptDecryptRoundTrip:
    """Test encrypt/decrypt round trip functionality."""

    def test_encrypt_decrypt_roundtrip_simple_string(self):
        """Test encryption and decryption round trip with simple string."""
        original_value = "hello world"

        encrypted_value = encrypt_content(original_value)
        decrypted_value = decrypt_content(encrypted_value)

        assert decrypted_value == original_value

    def test_encrypt_decrypt_roundtrip_complex_string(self):
        """Test encryption and decryption round trip with complex string."""
        original_value = "Complex string with numbers 123, symbols !@#$%, and unicode 🔒"

        encrypted_value = encrypt_content(original_value)
        decrypted_value = decrypt_content(encrypted_value)

        assert decrypted_value == original_value

    def test_encrypt_decrypt_roundtrip_multiline_string(self):
        """Test encryption and decryption round trip with multiline string."""
        original_value = """Multi-line string
        with different lines
        and various characters: !@#$%^&*()"""

        encrypted_value = encrypt_content(original_value)
        decrypted_value = decrypt_content(encrypted_value)

        assert decrypted_value == original_value

    def test_encrypt_decrypt_roundtrip_json_like_string(self):
        """Test encryption and decryption round trip with JSON-like string."""
        original_value = '{"key": "value", "number": 123, "nested": {"inner": "data"}}'

        encrypted_value = encrypt_content(original_value)
        decrypted_value = decrypt_content(encrypted_value)

        assert decrypted_value == original_value

    def test_encrypt_decrypt_roundtrip_multiple_values(self):
        """Test encryption and decryption round trip with multiple different values."""
        test_values = [
            "simple",
            "with spaces",
            "123456789",
            "special!@#$%characters",
            "émojis🚀andñoñó",
            "",  # empty string
            "a" * 1000,  # long string
        ]

        for original_value in test_values:
            encrypted_value = encrypt_content(original_value)
            decrypted_value = decrypt_content(encrypted_value)

            assert decrypted_value == original_value, f"Failed for value: {original_value}"

    def test_encrypt_decrypt_none_handling(self):
        """Test that None values are handled consistently."""
        # Test encrypt None -> None
        encrypted_none = encrypt_content(None)
        assert encrypted_none is None

        # Test decrypt None -> None
        decrypted_none = decrypt_content(None)
        assert decrypted_none is None

    def test_encrypt_different_results_decrypt_same_value(self):
        """Test that different encryptions of same value decrypt to same result."""
        original_value = "consistency_test"

        # Encrypt the same value multiple times
        encrypted1 = encrypt_content(original_value)
        encrypted2 = encrypt_content(original_value)
        encrypted3 = encrypt_content(original_value)

        # All encrypted values should be different (due to randomness)
        assert encrypted1 != encrypted2
        assert encrypted2 != encrypted3
        assert encrypted1 != encrypted3

        # But all should decrypt to the same original value
        assert decrypt_content(encrypted1) == original_value
        assert decrypt_content(encrypted2) == original_value
        assert decrypt_content(encrypted3) == original_value
