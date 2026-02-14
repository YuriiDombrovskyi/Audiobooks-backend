"""
Audiobook backend (Phase 1): Google OAuth, Drive discovery, file download.

Load .env in development only (production uses env vars directly). Add CORS,
global exception handler, optional DB init.
"""
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import ENV, FRONTEND_URL, SKIP_DB_INIT

# Load .env only in development; production should set env vars directly
if ENV == "development":
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from database import Base, engine
from auth import router as auth_router
from drive import router as drive_router

# Create DB tables if not skipping (production uses Alembic migrations)
if not SKIP_DB_INIT:
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Audiobook Backend",
    description="Phase 1: Auth, Drive root folder, eligible file discovery, download to per-user storage.",
)

# CORS: explicit origin, allow credentials (cookies). Never use "*" with cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL] if FRONTEND_URL else [],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions; log and return generic 500. Never leak stack traces."""
    # Let FastAPI handle HTTPException (validation, auth, etc.)
    if isinstance(exc, HTTPException):
        raise exc
    logging.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(drive_router)
