"""
Encryption of OAuth tokens at rest using Fernet (symmetric, from cryptography).

Tokens are encrypted before being stored in the User table and decrypted only
when needed for Google API calls. Handles None for optional refresh_token.
"""
import os

from cryptography.fernet import Fernet

FERNET_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY")
if not FERNET_KEY:
    raise RuntimeError("TOKEN_ENCRYPTION_KEY environment variable is required")
fernet = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)


def encrypt(value: str) -> str:
    """Encrypt a string (e.g. access_token or refresh_token) for storage."""
    return fernet.encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    """
    Decrypt a stored token. Returns None if value is None (e.g. optional refresh_token).
    """
    if value is None:
        return None
    return fernet.decrypt(value.encode()).decode()
