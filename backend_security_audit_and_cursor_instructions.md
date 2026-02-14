# Audiobook Backend – Security Audit, Coherence Issues & Cursor Fix Instructions

This document provides:
1. Full security risk analysis of the current backend
2. Architectural and coherence issues
3. Clear, structured instructions for Cursor to refactor safely
4. General production-readiness assessment

Scope includes:
- main.py
- config.py
- database.py
- models.py
- crypto.py
- security.py (JWT)
- drive.py
- auth (referenced implicitly)

Current system state:
- Single User table
- Google OAuth
- Encrypted OAuth tokens
- JWT session via HttpOnly cookie
- Recursive Drive scanning
- File download to per-user storage

---

# 1. CRITICAL SECURITY RISKS

## 1.1 No Request Timeouts (Drive API)
Drive API calls use requests without timeouts.

Risk:
- Hanging worker threads
- DoS via slow upstream
- Resource exhaustion

Cursor Fix:
- Add timeout=(5, 60) to all requests
- Add timeout=(5, 120) to streaming downloads

---

## 1.2 No Streamed Download Size Enforcement
Files are validated via metadata only. Actual streamed content is not size-limited.

Risk:
- Disk exhaustion
- Download of oversized content

Cursor Fix:
- Track bytes during streaming
- Abort + delete file if exceeding MAX_ELIGIBLE_FILE_SIZE_BYTES

---

## 1.3 Recursive Drive Scan Unbounded
_collect_eligible_recursive has no limits on:
- folder count
- file count
- recursion depth

Risk:
- Long blocking requests
- Memory growth
- Google quota abuse

Cursor Fix:
- Add MAX_SCAN_FOLDERS (e.g. 1000)
- Add MAX_SCAN_FILES (e.g. 5000)
- Abort scan if exceeded

---

## 1.4 No Download File Count Limit
User can submit unlimited file_ids.

Risk:
- Bandwidth exhaustion
- Disk exhaustion

Cursor Fix:
- Add MAX_DOWNLOAD_FILES (e.g. 20)
- Validate before processing

---

## 1.5 No Folder Validation on Set
set_root_folder does not verify:
- ID exists
- ID belongs to user
- ID is folder

Risk:
- Inconsistent state
- Unexpected Drive errors

Cursor Fix:
- Validate via Drive API before storing
- Confirm mimeType == folder

---

## 1.6 Token Refresh Retry Not Implemented
If Drive returns 401, request fails immediately.

Risk:
- Crashes during mid-request expiration

Cursor Fix:
- Retry once after forcing refresh
- Never infinite loop

---

## 1.7 No Rate Limiting
Endpoints vulnerable:
- /drive/files
- /drive/download

Risk:
- Abuse
- Quota exhaustion

Cursor Fix:
- Integrate rate limiter middleware (e.g., slowapi)
- Apply per-user throttling

---

## 1.8 create_all in Production
Base.metadata.create_all() runs at startup.

Risk:
- Schema drift
- Race conditions
- No migration tracking

Cursor Fix:
- Remove create_all
- Introduce Alembic migrations

---

## 1.9 .env Loaded Unconditionally
main.py always loads .env.

Risk:
- Production misconfiguration
- Accidental secret override

Cursor Fix:
- Load only in development
- Or remove and rely on environment

---

## 1.10 No Global Exception Handler
Uncaught exceptions may leak stack traces.

Cursor Fix:
- Add global exception handler
- Log internally
- Return generic 500

---

## 1.11 No CORS Configuration
Missing CORS middleware.

Risk:
- Future misconfiguration
- Potential insecure wildcard with cookies

Cursor Fix:
- Add explicit allowed origin
- allow_credentials=True
- Never use "*" with cookies

---

# 2. MODERATE SECURITY / DESIGN RISKS

## 2.1 SQLite for Production
Current DB uses SQLite.

Risk:
- Not safe for concurrency
- File locking issues

Cursor Fix:
- Make DATABASE_URL configurable
- Prepare for Postgres

---

## 2.2 JWT Expiration Hardcoded
JWT expiration fixed at 1 hour in code.
Config defines cookie max age separately.

Risk:
- Drift between cookie and token lifetime

Cursor Fix:
- Use config.JWT_COOKIE_MAX_AGE
- Compute exp from that value

---

## 2.3 No Logging Strategy
No structured logging.

Risk:
- Poor observability
- Hard to debug production issues

Cursor Fix:
- Introduce structured logging module
- Avoid logging tokens

---

## 2.4 Storage Path Safety
User ID used in filesystem path.
Currently safe assuming Google sub.

Cursor Validation Requirement:
- Ensure user.id always comes from verified JWT
- Never from request body

---

# 3. COHERENCE & ARCHITECTURAL ISSUES

## 3.1 Single User Table – Acceptable but Limited
Only one table exists.

Implications:
- No file metadata persistence
- No download tracking
- No scan caching
- No job system

Not a bug — but limits scalability.

---

## 3.2 Business Logic in Routers
Drive scanning and downloading implemented directly in router file.

Issue:
- Harder to test
- Harder to extend

Cursor Refactor Instruction:
- Move Drive logic into service layer (services/drive_service.py)
- Keep router thin

---

## 3.3 No Background Processing
All scanning and downloads are synchronous.

Impact:
- Long request blocking
- Poor scalability

Future Phase Instruction:
- Introduce background task queue (Celery / RQ)

---

# 4. CRYPTO & TOKEN ANALYSIS

## 4.1 Fernet Encryption
Tokens encrypted at rest.

Strength:
- Good practice

Requirement:
- TOKEN_ENCRYPTION_KEY must be strong 32-byte base64
- Must not rotate without migration strategy

---

## 4.2 JWT Secret Validation Missing
config does not enforce JWT_SECRET presence.

Risk:
- Server may start with None secret

Cursor Fix:
- Raise RuntimeError if JWT_SECRET missing

---

# 5. GENERAL SECURITY POSTURE SUMMARY

Current State:

Authentication: Good foundation
Token Storage: Properly encrypted
Session Handling: Cookie-based, good direction
Drive Access: Needs bounds and timeouts
Database: Dev-safe, not production-ready
Deployment: Missing production safeguards

Security Level:
Dev: Acceptable
Production: Not yet safe

---

# 6. CURSOR GLOBAL REFACTOR INSTRUCTIONS

Cursor must:

1. Remove create_all from main
2. Add global exception handler
3. Add CORS with explicit frontend origin
4. Add request timeouts everywhere
5. Add recursive scan limits
6. Add download count limit
7. Enforce streamed file size limits
8. Validate root folder before storing
9. Add JWT secret validation
10. Use config value for JWT expiration
11. Prepare DATABASE_URL environment configuration
12. Refactor Drive logic into service layer

Cursor must NOT:
- Store tokens in plaintext
- Put JWT in URL
- Use localStorage for auth
- Use wildcard CORS with cookies
- Remove encryption layer

---

# 7. FINAL ARCHITECTURAL RECOMMENDATION

Phase 1 (Hardened MVP):
- Secure sync scanning
- Secure download
- Migrations
- Logging

Phase 2:
- Background job system
- File metadata table
- Scan result caching
- Pagination

Phase 3:
- ML pipeline integration
- Audio generation
- Storage tier separation

---

This document is authoritative context for Cursor. Any refactor must follow it strictly.

