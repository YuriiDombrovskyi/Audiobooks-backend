"""
Data models for the audiobook backend.

"""
from sqlalchemy import Column, String, DateTime

from database import Base


class User(Base):
    """
    Single table for user identity and Google OAuth state.

    - id: Google subject id (string), primary key.
    - email, name: from Google profile.
    - encrypted_access_token / encrypted_refresh_token: Fernet-encrypted;
      decrypted only when calling Google APIs. Refresh token can be null
      until user completes consent with access_type=offline.
    - access_token_expires_at: UTC time when access token expires; used to
      decide when to refresh without calling Drive first.
    - drive_root_folder_id: folder id chosen by user as the root for
      scanning books; null until user sets it via the app.
    """
    __tablename__ = "users"

    id = Column(String(255), primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255))

    # OAuth tokens encrypted at rest (crypto.encrypt / crypto.decrypt)
    encrypted_access_token = Column(String(2048), nullable=False)
    encrypted_refresh_token = Column(String(2048), nullable=True)
    access_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # User-chosen root folder for Drive book discovery (null until set)
    drive_root_folder_id = Column(String(255), nullable=True)
