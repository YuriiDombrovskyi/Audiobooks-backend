"""
JWT creation and verification for session management.

Sessions are identified by a short-lived JWT stored in an HttpOnly cookie
(set in auth router). Algorithm: HS256; secret must be set in config.
Expiration matches JWT_COOKIE_MAX_AGE for coherence.
"""
from datetime import datetime, timedelta, UTC

from jose import jwt, JWTError

from config import JWT_SECRET, JWT_ALGORITHM, JWT_COOKIE_MAX_AGE


def create_jwt(user_id: str) -> str:
    """Build a JWT for the given user id (Google sub); exp = now + JWT_COOKIE_MAX_AGE."""
    payload = {
        "sub": user_id,
        "exp": datetime.now(UTC) + timedelta(seconds=JWT_COOKIE_MAX_AGE),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    """Decode and verify JWT; raises JWTError if invalid or expired."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
