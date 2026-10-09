# main.py — FastAPI application entry point

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api.routes import router
from app.core.config import settings
from app.database.connection import engine, Base
import app.database.models  # noqa: F401 — ensures models are registered on Base

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description="SakhiPune AI — NLP-Based Women Empowerment & Support System for Pune",
)

# Allow the HTML/JS frontend to call this API from the browser.
# Local development origins are always included.
# Production Vercel domain is injected via the ALLOWED_ORIGINS environment variable.
_extra_origins = [
    o.strip()
    for o in settings.ALLOWED_ORIGINS.split(",")
    if o.strip()
]
_cors_origins = [
    "null",                          # file:// opened directly in browser
    settings.FRONTEND_URL,           # http://localhost:5500
    settings.FRONTEND_URL_ALT,       # http://127.0.0.1:5500
    "http://localhost:5501",
    "http://127.0.0.1:5501",
    "http://localhost:8080",         # python -m http.server 8080
    "http://127.0.0.1:8080",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost",
    "http://127.0.0.1",
] + _extra_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)

# All routes are defined in routes.py and registered here.
# Mounted under /api so URLs match on Vercel (/api/recommend etc.)
# The frontend's apiPath() helper also prepends /api in all environments.
app.include_router(router, prefix="/api")


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request, exc):
    """Return one safe validation shape for malformed API requests."""
    logger.warning("Validation error on %s", request.url.path)
    return JSONResponse(
        status_code=422,
        content={"error": "VALIDATION_ERROR", "message": "Please provide a valid support request."},
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request, exc):
    """Hide internal details while retaining a server-side diagnostic log."""
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": "Something went wrong. Please try again later."},
    )


@app.on_event("startup")
def create_tables():
    """
    Attempts to create database tables on startup.
    If PostgreSQL is not running, logs a warning and continues —
    the app still starts so NLP endpoints remain available.
    """
    try:
        Base.metadata.create_all(bind=engine)
        print("INFO:     Database tables created / confirmed.")
    except Exception as e:
        print(f"WARNING:  Database not available — skipping table creation. ({e.__class__.__name__})")
        print("WARNING:  Start PostgreSQL and set DATABASE_URL in backend/.env to enable DB features.")
