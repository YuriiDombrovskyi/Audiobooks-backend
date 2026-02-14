# Audiobook Platform – Project Context

## 1. Project Overview
This project is a **local-first, privacy-focused audiobook generation web application**. The goal is to allow users to convert books stored in their **Google Drive** into high-quality audiobooks using **locally hosted neural text-to-speech (TTS) models**. The system prioritizes **audio quality, correctness, and architectural clarity over speed**.

The project is designed to be:
- **Resume-grade** (demonstrates system design, security, OAuth, async processing, ML pipelines)
- **Practically usable** by non-technical users (family)
- **Cost-free to operate** (no paid APIs, local ML inference)

The application is built as a **web app** with:
- Backend: **FastAPI (Python)**
- Frontend: **React**
- ML/TTS: **Local neural TTS (XTTS v2 / Coqui)**

---

## 2. Core Features (End-State Vision)

### Authentication & Authorization
- Login via **Google OAuth 2.0 (Authorization Code Flow)**
- Backend-owned OAuth tokens
- JWT-based session management via **HttpOnly cookies**
- Secure token storage (encrypted at rest)

### Google Drive Integration
- User grants **read-only** access to Drive
- App automatically discovers books in a configured root folder
- Supported input formats:
  - PDF (primary, ~90%)
  - EPUB
  - DOCX
- Google-native docs are ignored or exported explicitly

### Audiobook Generation (Later Phases)
- Automatic chapter detection
- Text cleanup (headers, footers, page numbers)
- Dialogue vs narration detection
- Multi-voice narration (narrator + characters)
- Configurable quality vs speed trade-offs
- MP3 output (default)

### User Experience
- Web UI for:
  - Browsing eligible books
  - Selecting chapters or full books
  - Tracking processing jobs
  - Downloading generated audiobooks

---

## 3. Current Implementation Phase (Phase 1)

**Scope of the current phase:**
- Secure backend authentication
- Google Drive file discovery
- File download to local storage
- No ML / TTS yet

After Phase 1, the system allows a user to:
1. Log in via Google
2. Grant Drive access
3. View ML-eligible files
4. Select files
5. Download them to backend-local storage

This phase establishes the **security model, API contracts, and storage layout** that all future phases build upon.

---

## 4. High-Level Architecture

```
Browser (React)
   |
   | HTTPS (JWT via HttpOnly cookie)
   v
Backend (FastAPI)
   |
   | OAuth 2.0
   v
Google OAuth + Drive APIs

Backend Local Storage
(storage/users/<user_id>/...)
```

Key architectural principles:
- Frontend **never** talks directly to Google APIs
- OAuth tokens are **never exposed** to the browser
- ML runs locally (client or backend), never in the cloud

---

## 5. Security Model (Important)

### OAuth
- Google OAuth 2.0 Authorization Code Flow
- `access_token` + `refresh_token` owned by backend
- Refresh tokens encrypted at rest
- Automatic access token refresh

### Sessions
- Backend issues short-lived JWTs
- JWT stored in **HttpOnly, SameSite cookies**
- No tokens in URLs or localStorage

### Multi-User Isolation
- Per-user database records
- Per-user filesystem namespaces
- No shared storage paths

---

## 6. Backend Responsibilities

- OAuth login and token lifecycle management
- Secure user/session management
- Google Drive API integration
- File eligibility filtering
- File download and storage
- (Later) job orchestration for ML pipelines

Backend stack:
- FastAPI
- SQLAlchemy + SQLite (later Postgres)
- Requests
- python-jose (JWT)
- cryptography (token encryption)

---

## 7. Frontend Responsibilities

- Initiate login flow
- Display authentication state
- Fetch available Drive files
- Allow file selection
- Trigger backend downloads
- Display progress and errors

Frontend stack:
- React
- Fetch / Axios
- Cookie-based auth (no token handling)

---

## 8. Storage Layout (Authoritative)

```
storage/
  users/
    user_<id>/
      drive/
        raw/        # downloaded source books
        processed/  # cleaned / split text
      audio/
        chapters/
        full_books/
```

All ML pipelines consume data from this structure.

---

## 9. ML / TTS (Deferred)

Planned later-phase components:
- Text extraction (PDF/EPUB/DOCX)
- NLP cleanup & segmentation
- Dialogue detection
- Emotion tagging
- Multi-voice neural TTS (XTTS v2)

Constraints:
- Fully local inference
- No paid APIs
- Speed is secondary to quality

---

## 10. Non-Goals

- No public SaaS hosting
- No paid cloud services
- No real-time audio generation
- No DRM handling

---

## 11. Development Principles

- Security over convenience
- Clarity over premature optimization
- Every feature must justify its complexity
- Architecture must support Docker & offline usage

---

## 12. Intended Use of This Document

This document is intended to be used as:
- **Cursor IDE context**
- Architectural reference during coding
- Alignment guide for future ML integration
- Resume / portfolio explanation

Any generated code should:
- Respect the security model
- Preserve separation of concerns
- Avoid shortcuts that break future phases
