"""
index.py — Vercel Python serverless entry point for SakhiPune AI.

Vercel's Python runtime looks for a file named index.py (or api/index.py).
This module must expose a WSGI/ASGI app named `app` or `handler`.

This file does NOT create a second FastAPI application.
It simply imports and re-exports the existing FastAPI app from backend/app/main.py.

The `app` object here IS the same FastAPI instance — no duplication of routes.
"""

import sys
import os

# Ensure the backend package is importable from the project root.
# Vercel runs from the project root, not from inside backend/.
_backend_path = os.path.join(os.path.dirname(__file__), "backend")
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

# Import the existing FastAPI application — do not create a new one.
from app.main import app  # noqa: F401  — re-exported for Vercel

# Vercel expects the ASGI app to be named `app` at module level.
# Nothing else is needed here.
