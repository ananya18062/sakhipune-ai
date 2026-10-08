"""counselling_service.py — Counselling support for SakhiPune AI.

Verified data sources (PostgreSQL, September 2026)
────────────────────────────────────────────────────
  • iCALL Psychosocial Helpline (TISS)    — 9152987821
  • Vandrevala Foundation Helpline         — 18602662345
  • iCall Email Counselling (TISS)         — https://icallhelpline.org
  • Pune Bharosa Cell – Counselling        — 1091
  • iCall Marathi Counselling Support      — 9152987821

IMPORTANT:
  This service provides information about counselling resources only.
  It does not provide medical diagnosis, therapy or clinical advice.
  Users in crisis should call iCALL (9152987821) or Vandrevala (1860-2662-345).
"""

from __future__ import annotations
import logging
from typing import Any
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.database.models import SupportResource
from app.services.api_clients.base_client import BaseAPIClient, fetch_with_fallback, normalize_resource
from app.services.resource_normalizer import orm_to_normalized as _orm_to_normalized
from app.core.config import settings

logger = logging.getLogger(__name__)
COUNSELLING_CATEGORY = "Counselling"

MARATHI_COUNSELLING_KEYWORDS = {"marathi", "mr", "मराठी"}
CRISIS_COUNSELLING_KEYWORDS = {
    "crisis", "urgent", "immediate", "emergency", "suicid",
    "harm", "abuse", "trauma",
}

_COUNSELLING_API_URL: str = getattr(settings, "COUNSELLING_API_URL", "")
_client: BaseAPIClient | None = (
    BaseAPIClient(base_url=_COUNSELLING_API_URL, timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS)
    if _COUNSELLING_API_URL else None
)


def _resource_text(r: dict[str, Any]) -> str:
    return " ".join([r.get("name",""), r.get("description",""), r.get("location","")]).lower()


def _load_counselling_from_db(db: Session) -> list[dict[str, Any]]:
    try:
        rows = (db.query(SupportResource)
                .filter(SupportResource.category.ilike(COUNSELLING_CATEGORY))
                .order_by(SupportResource.name).all())
        return [_orm_to_normalized(r) for r in rows]
    except SQLAlchemyError:
        logger.exception("DB query failed in counselling_service")
        return []


def get_counselling_resources(db: Session) -> list[dict[str, Any]]:
    """Return all verified Counselling resources. Never raises."""
    if _client:
        try:
            return fetch_with_fallback(
                _client, path="", source="Counselling API",
                fallback_loader=lambda: _load_counselling_from_db(db),
                params={"category": "counselling", "location": "Pune"},
            )
        except Exception:
            logger.exception("Unexpected error in counselling live fetch; using DB fallback")
    return _load_counselling_from_db(db)


def get_marathi_counselling_resources(db: Session) -> list[dict[str, Any]]:
    """Return Marathi-language counselling resources.
    Falls back to full list if none found."""
    all_c = get_counselling_resources(db)
    mr = [r for r in all_c
          if r.get("language") == "mr"
          or any(kw in _resource_text(r) for kw in MARATHI_COUNSELLING_KEYWORDS)]
    return mr if mr else all_c


def get_all_counselling_resources(db: Session) -> list[dict[str, Any]]:
    return get_counselling_resources(db)


def describe_counselling_sources() -> dict[str, Any]:
    return {
        "live_api_configured": bool(_COUNSELLING_API_URL),
        "live_api_url": _COUNSELLING_API_URL or None,
        "fallback": "PostgreSQL verified data",
        "categories_served": [COUNSELLING_CATEGORY],
        "crisis_note": (
            "For immediate mental health crisis support call iCALL at 9152987821 "
            "or Vandrevala Foundation at 1860-2662-345 (24-hour, free, confidential). "
            "This service provides counselling resource information only — it does not "
            "provide clinical advice or diagnosis."
        ),
        "verified_resources": [
            {"name": "iCALL Psychosocial Helpline (TISS)", "source": "icallhelpline.org / TISS — 9152987821"},
            {"name": "Vandrevala Foundation Helpline", "source": "vandrevalafoundation.com — 1860-2662-345"},
            {"name": "iCall Email Counselling (TISS)", "source": "icallhelpline.org"},
            {"name": "Pune Bharosa Cell – Counselling Division", "source": "Pune Police — 1091"},
            {"name": "iCall Marathi Counselling Support", "source": "icallhelpline.org / TISS — 9152987821"},
        ],
        "note": (
            "No public unauthenticated JSON API exists for counselling services "
            "in Pune/Maharashtra as of September 2026. "
            "Set COUNSELLING_API_URL in .env when available. "
            "Current data is served from verified PostgreSQL records."
        ),
    }
