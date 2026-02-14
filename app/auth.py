"""
Google OAuth 2.0 login, callback, session cookie, and current-user dependency.

- Login redirects to Google with a CSRF state stored in a short-lived cookie.
- Callback validates state, exchanges code for tokens, stores encrypted tokens
  on User, sets JWT in HttpOnly cookie, redirects to frontend (no token in URL).
- /me returns current user when session cookie is valid.
- /logout clears the session cookie.
- get_current_user dependency reads JWT from cookie and returns User (for drive and others).
- get_valid_access_token(user, db) returns a valid access_token, refreshing if needed.
"""
import secrets
from datetime import datetime, timedelta, UTC

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from config import (
    FRONTEND_URL,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    JWT_COOKIE_MAX_AGE,
    JWT_COOKIE_NAME,
    OAUTH_STATE_COOKIE_NAME,
    OAUTH_STATE_MAX_AGE,
    SECURE_COOKIES,
)
from crypto import decrypt, encrypt
from database import get_db
from models import User
from security import create_jwt, decode_jwt

router = APIRouter(prefix="/auth")

# Cookie flags: HttpOnly (no JS access), SameSite=Lax (CSRF mitigation), Secure in production is set per-response
def _cookie_kwargs(secure: bool = False) -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": secure,
        "path": "/",
    }


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency: read JWT from session cookie, decode it, load User.
    Raises 401 if cookie missing or JWT invalid/expired or user not found.
    """
    token = request.cookies.get(JWT_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_jwt(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid session")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_valid_access_token(user: User, db: Session, *, force_refresh: bool = False) -> str:
    """
    Return a valid Google access token for this user, refreshing if expired or
    expiring within 5 minutes (or always when force_refresh=True, for retry after 401).
    Updates user.encrypted_* and access_token_expires_at in DB when refresh is performed.
    Raises 401 if refresh token is missing or refresh fails.
    """
    access_token = decrypt(user.encrypted_access_token)
    expires_at = user.access_token_expires_at
    now = datetime.now(UTC)
    # Refresh if force_refresh, or no expiry info, or expired, or expiring soon
    if force_refresh or not expires_at or now >= expires_at - timedelta(minutes=5):
        refresh_token = decrypt(user.encrypted_refresh_token)
        if not refresh_token:
            raise HTTPException(
                status_code=401,
                detail="Session expired; please log in again to grant Drive access",
            )
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=(5, 30),
        )
        data = resp.json()
        if "error" in data:
            raise HTTPException(
                status_code=401,
                detail="Failed to refresh Google token; please log in again",
            )
        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        user.encrypted_access_token = encrypt(access_token)
        user.access_token_expires_at = now + timedelta(seconds=expires_in)
        if data.get("refresh_token"):
            user.encrypted_refresh_token = encrypt(data["refresh_token"])
        db.commit()
    return access_token


@router.get("/google/login")
def google_login(response: Response):
    """
    Redirect to Google OAuth consent. Sets a short-lived cookie with a random
    state value and includes the same state in the redirect URL so the callback
    can verify the request was not forged (CSRF protection).
    """
    state = secrets.token_urlsafe(32)
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        "&response_type=code"
        "&scope=openid email profile https://www.googleapis.com/auth/drive.readonly"
        "&access_type=offline"
        "&prompt=consent"
        f"&state={state}"
    )
    redirect = RedirectResponse(url=url)
    redirect.set_cookie(
        OAUTH_STATE_COOKIE_NAME,
        state,
        max_age=OAUTH_STATE_MAX_AGE,
        **_cookie_kwargs(secure=SECURE_COOKIES),
    )
    return redirect


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Handle redirect from Google. Validates state cookie (CSRF), exchanges code
    for tokens, creates/updates User with encrypted tokens, sets session cookie,
    redirects to frontend success page (no JWT in URL).
    """
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    state_cookie = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    if not state_cookie or not secrets.compare_digest(state, state_cookie):
        raise HTTPException(status_code=400, detail="Invalid or expired state; please try logging in again")

    token_res = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": GOOGLE_REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=(5, 30),
    )
    token_data = token_res.json()
    if "error" in token_data:
        raise HTTPException(
            status_code=400,
            detail=f"Token exchange failed: {token_data.get('error_description', token_data['error'])}",
        )

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail="Token exchange did not return access_token",
        )
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

    userinfo_res = requests.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=(5, 30),
    )
    userinfo_res.raise_for_status()
    userinfo = userinfo_res.json()

    user_id = userinfo.get("sub")
    email = userinfo.get("email")
    if not user_id or not email:
        raise HTTPException(
            status_code=400,
            detail="Google userinfo missing sub or email",
        )
    user = db.get(User, user_id)
    if not user:
        user = User(
            id=user_id,
            email=email,
            name=userinfo.get("name"),
            encrypted_access_token=encrypt(access_token),
            encrypted_refresh_token=encrypt(refresh_token) if refresh_token else None,
            access_token_expires_at=expires_at,
        )
        db.add(user)
    else:
        user.encrypted_access_token = encrypt(access_token)
        if refresh_token:
            user.encrypted_refresh_token = encrypt(refresh_token)
        user.access_token_expires_at = expires_at
    db.commit()

    jwt_token = create_jwt(user.id)
    redirect = RedirectResponse(url=f"{FRONTEND_URL}/login/success")
    # Set session cookie so frontend can call /auth/me and other APIs with credentials
    redirect.set_cookie(
        JWT_COOKIE_NAME,
        jwt_token,
        max_age=JWT_COOKIE_MAX_AGE,
        **_cookie_kwargs(secure=SECURE_COOKIES),
    )
    # Clear state cookie
    redirect.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/")
    return redirect


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    """Return current user profile (id, email, name). Requires valid session cookie."""
    return {"id": user.id, "email": user.email, "name": user.name}


@router.post("/logout")
def logout(response: Response):
    """
    Clear the session cookie so the client is logged out. Frontend should
    redirect to login after calling this.
    """
    response.delete_cookie(JWT_COOKIE_NAME, path="/")
    return {"ok": True}
