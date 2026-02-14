"""
Application configuration from environment variables.

Load with python-dotenv in main so env vars are available before imports.
Validates critical secrets at module load; missing values raise RuntimeError.
"""
import os

# --- Required (raise if missing) ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
JWT_SECRET = os.getenv("JWT_SECRET")

for name, val in [
    ("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID),
    ("GOOGLE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET),
    ("GOOGLE_REDIRECT_URI", GOOGLE_REDIRECT_URI),
    ("JWT_SECRET", JWT_SECRET),
]:
    if not val or not str(val).strip():
        raise RuntimeError(f"Required env var {name} is missing or empty")

JWT_ALGORITHM = "HS256"

# --- Optional with defaults ---
# Frontend URL for post-login redirect; cookie is set by backend, no token in URL
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")

# Session cookie: JWT lifetime and cookie max_age should match
JWT_COOKIE_NAME = os.getenv("JWT_COOKIE_NAME", "session")
_JWT_MAX_AGE_RAW = os.getenv("JWT_COOKIE_MAX_AGE", "3600")
try:
    JWT_COOKIE_MAX_AGE = max(60, int(_JWT_MAX_AGE_RAW))
except ValueError:
    JWT_COOKIE_MAX_AGE = 3600

# OAuth CSRF: cookie name for state parameter, short-lived
OAUTH_STATE_COOKIE_NAME = os.getenv("OAUTH_STATE_COOKIE_NAME", "oauth_state")
OAUTH_STATE_MAX_AGE = 600  # 10 minutes

# Storage root; user files go under storage/users/user_<id>/...
STORAGE_ROOT = os.getenv("STORAGE_ROOT", "storage")

# Max file size for eligible books (bytes), e.g. 50 MB for PDFs
_MAX_SIZE_RAW = os.getenv("MAX_ELIGIBLE_FILE_SIZE_BYTES", "52428800")
try:
    MAX_ELIGIBLE_FILE_SIZE_BYTES = max(0, int(_MAX_SIZE_RAW))
except ValueError:
    MAX_ELIGIBLE_FILE_SIZE_BYTES = 52428800

# Recursive Drive scan limits (prevent unbounded scans, quota abuse)
def _int_env(key: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(key, str(default))))
    except ValueError:
        return default

MAX_SCAN_FOLDERS = _int_env("MAX_SCAN_FOLDERS", 1000)
MAX_SCAN_FILES = _int_env("MAX_SCAN_FILES", 5000)

# Download: max files per request
MAX_DOWNLOAD_FILES = _int_env("MAX_DOWNLOAD_FILES", 20)

# Request timeouts (connect, read) in seconds
DRIVE_REQUEST_TIMEOUT = (5, 60)  # connect 5s, read 60s
DRIVE_DOWNLOAD_TIMEOUT = (5, 120)  # streaming download: 120s read

# Secure cookie flag (set True in production over HTTPS)
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "false").lower() in ("1", "true", "yes")

# Database URL (SQLite default; use Postgres URL in production)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# Skip create_all at startup (set in production when using Alembic migrations)
SKIP_DB_INIT = os.getenv("SKIP_DB_INIT", "false").lower() in ("1", "true", "yes")

# Environment: development | production (affects .env loading, error details)
ENV = os.getenv("ENV", "development").lower()
