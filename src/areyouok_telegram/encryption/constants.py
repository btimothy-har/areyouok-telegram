"""Encryption constants for the application."""

import base64
import hashlib

from areyouok_telegram.config import USER_ENCRYPTION_SALT

# Static application-level Fernet key for metadata encryption
# Derived from USER_ENCRYPTION_SALT, computed once at module load
salt_hash = hashlib.sha256(USER_ENCRYPTION_SALT.encode()).digest()
APPLICATION_FERNET_KEY = base64.urlsafe_b64encode(salt_hash).decode("utf-8")
