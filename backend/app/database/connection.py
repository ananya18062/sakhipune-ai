# connection.py — PostgreSQL database connection using SQLAlchemy
#
# Provides three things used throughout the app:
#   engine       — the SQLAlchemy connection to PostgreSQL
#   SessionLocal — a factory for creating database sessions
#   Base         — the base class all ORM models will inherit from

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
# DATABASE_URL comes from config (loaded from .env or Vercel environment vars).
# pool_pre_ping=True checks the connection is alive before each use —
# this prevents errors if PostgreSQL restarts while the app is running.
#
# connect_args: Neon (and most cloud PostgreSQL) requires SSL.
# sslmode=require is passed explicitly as a fallback in case it is not
# already present in the DATABASE_URL query string.
_db_url = settings.DATABASE_URL
_connect_args = {}
if "neon.tech" in _db_url or "sslmode" not in _db_url:
    _connect_args = {"sslmode": "require"}

engine = create_engine(
    _db_url,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

# ── Session factory ───────────────────────────────────────────────────────────
# Each request gets its own session via get_db() (defined below)
# autocommit=False — we commit manually after writes
# autoflush=False  — changes are not sent to DB until we call commit/flush
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ── Base class ────────────────────────────────────────────────────────────────
# All SQLAlchemy ORM models will inherit from this Base
# Defined here so models.py can import it from one place
Base = declarative_base()


# ── Dependency for FastAPI routes ─────────────────────────────────────────────
def get_db():
    """
    Yields a database session for use in a FastAPI route.
    Automatically closes the session when the request is done.

    Usage in a route:
        from app.database.connection import get_db
        from sqlalchemy.orm import Session
        from fastapi import Depends

        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
