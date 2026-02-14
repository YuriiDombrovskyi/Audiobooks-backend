# Audiobook Backend (Phase 1)

Backend for a local-first, privacy-focused audiobook app: Google OAuth, Drive root folder selection, discovery of eligible books (PDF, EPUB, DOCX under a size limit), and download to per-user storage. No ML/TTS in this phase.

## Implementation Overview (After Latest Changes)

### Authentication & Sessions

- **Google OAuth 2.0 (Authorization Code Flow)**  
  - `GET /auth/google/login` redirects to Google with a **CSRF `state`** parameter.  
  - The `state` is stored in a short-lived **HttpOnly cookie** (`oauth_state`).  
  - On callback, the backend compares the `state` from the URL with the cookie; if they don’t match, the request is rejected (CSRF protection).

- **Callback**  
  - Exchanges the authorization code for `access_token` and `refresh_token`.  
  - User profile is fetched from Google (id = `sub`, email, name).  
  - **Tokens are encrypted** with Fernet (see `crypto.py`) and stored on the **User** model.  
  - A **session JWT** is created and set in an **HttpOnly, SameSite=Lax** cookie (`session`).  
  - Redirect goes to `FRONTEND_URL/login/success` with **no token in the URL**.

- **Session usage**  
  - Protected routes use the **`get_current_user`** dependency, which reads the JWT from the **cookie** (not from query or body).  
  - `GET /auth/me` returns the current user.  
  - `POST /auth/logout` clears the session cookie.

- **Token refresh**  
  - Before any Google Drive API call, the backend uses **`get_valid_access_token(user, db)`**.  
  - If the access token is expired or expiring within 5 minutes, it is refreshed using the stored refresh token; the new access token (and optional new refresh token) is encrypted and saved.  
  - This keeps Drive operations working without re-login.

### Database (Single User Table)

- **User** (in `models.py`):  
  - `id` (string, PK) = Google `sub`  
  - `email`, `name`  
  - `encrypted_access_token`, `encrypted_refresh_token` (Fernet-encrypted)  
  - `access_token_expires_at` (used to decide when to refresh)  
  - `drive_root_folder_id` (user-chosen root folder for Drive; nullable)

There is no separate OAuth table; all token data lives on `User` and is encrypted at rest.

### Google Drive Flow

1. **Set root folder**  
   - After login, the user chooses a root folder (e.g. via frontend UI).  
   - Frontend calls `POST /drive/root-folder` with `{"folder_id": "..."}`.  
   - We store `drive_root_folder_id` on the user.

2. **List eligible files**  
   - `GET /drive/files` uses the user’s **root folder** and **recursively** lists all files in that folder and its subfolders.  
   - Only **eligible** files are returned: MIME type in `{PDF, EPUB, DOCX}` and **size ≤ 50 MB** (configurable via `MAX_ELIGIBLE_FILE_SIZE_BYTES`).  
   - Implemented with paginated Drive API calls and in-memory recursion (no shared storage between users).

3. **Download**  
   - `POST /drive/download` with body `{"file_ids": ["id1", "id2", ...]}`.  
   - The backend **recomputes** the eligible set under the user’s root; only file IDs in that set are allowed.  
   - Files are saved under **per-user paths**:  
     `storage/users/user_<id>/drive/raw/<safe_filename>`.  
   - Filenames are sanitized (path separators and reserved characters removed) to avoid path traversal and overwrites; duplicates get a numeric suffix.

### Security Summary

- **OAuth**: Authorization Code Flow, state parameter for CSRF, tokens only on backend.  
- **Tokens at rest**: Encrypted with Fernet (`TOKEN_ENCRYPTION_KEY`).  
- **Sessions**: JWT in HttpOnly cookie; no token in URL or localStorage.  
- **Drive**: Access token refreshed automatically; only files under the user’s root and passing eligibility checks can be listed or downloaded.  
- **Storage**: Strict per-user directories and safe filenames.

### Project Layout

```
app/
  main.py       # FastAPI app, dotenv load, router include
  config.py     # Env-based config (OAuth, JWT, cookie, storage, size limit)
  database.py   # SQLite engine, SessionLocal, get_db dependency
  models.py     # User (single table with encrypted tokens and root folder)
  crypto.py     # Fernet encrypt/decrypt for tokens
  security.py   # JWT create/decode
  auth.py       # OAuth login/callback, cookie, get_current_user, get_valid_access_token, /me, /logout
  drive.py      # /root-folder, /files (recursive eligible), /download (validated, per-user paths)
storage/
  users/
    user_<id>/
      drive/
        raw/    # downloaded books
```

### Running the Backend

1. Copy `.env.example` to `.env` and set:
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
   - `JWT_SECRET`
   - `TOKEN_ENCRYPTION_KEY` (generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
   - `FRONTEND_URL` (e.g. `http://localhost:3000`)

2. Install and run:

   ```bash
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
   (Run from project root; `.env` in project root is loaded automatically.)

   If you had a previous version of the backend with a different schema, remove `app/app.db` (or the path where SQLite DB lives) and restart so tables are recreated.

3. Frontend must call the API with **credentials** (e.g. `fetch(..., { credentials: 'include' })`) so the session cookie is sent.

### API Summary

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /health | — | Health check |
| GET | /auth/google/login | — | Redirect to Google OAuth (sets state cookie) |
| GET | /auth/google/callback | — | OAuth callback; sets session cookie, redirects to frontend |
| GET | /auth/me | Cookie | Current user |
| POST | /auth/logout | — | Clear session cookie |
| GET | /drive/root-folder | Cookie | Get current root folder id |
| POST | /drive/root-folder | Cookie | Set root folder (body: `{"folder_id": "..."}`) |
| GET | /drive/files | Cookie | List eligible files under root (recursive) |
| POST | /drive/download | Cookie | Download file ids (body: `{"file_ids": ["..."]}`) |
