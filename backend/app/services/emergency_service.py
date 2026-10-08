"""emergency_service.py — Emergency and Safety support for SakhiPune AI.

Verified data sources (PostgreSQL, September 2026)
────────────────────────────────────────────────────
  • Police Emergency Helpline       — 100
  • Women Helpline 1091             — 1091
  • National Emergency Ambulance    — 108
  • Pune Police Bharosa Cell        — 1091
  • National Women Helpline 181     — 181

CRITICAL SAFETY NOTE:
  For life-threatening emergencies call 100 (Police) or 112 (National Emergency).
  This service returns verified emergency resource information only.
  SakhiPune AI does NOT directly provide emergency assistance.
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
EMERGENCY_CATEGORY = "Emergency"

# Emergency resources always shown first — never filtered out by preference logic
CRITICAL_HELPLINE_NAMES = {
    "Police Emergency Helpline",
    "National Emergency Ambulance Service",
    "Women Helpline 1091",
    "National Women Helpline 181",
}

_EMERGENCY_API_URL: str = getattr(settings, "EMERGENCY_API_URL", "")
_client: BaseAPIClient | None = (
    BaseAPIClient(base_url=_EMERGENCY_API_URL, timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS)
    if _EMERGENCY_API_URL else None
)


def _load_emergency_from_db(db: Session) -> list[dict[str, Any]]:
    try:
        rows = (db.query(SupportResource)
                .filter(SupportResource.category.ilike(EMERGENCY_CATEGORY))
                .order_by(SupportResource.name).all())
        return [_orm_to_normalized(r) for r in rows]
    except SQLAlchemyError:
        logger.exception("DB query failed in emergency_service")
        return []


def get_emergency_resources(db: Session) -> list[dict[str, Any]]:
    """Return all verified Emergency resources.

    Critical helplines (Police 100, Ambulance 108, Women Helpline 1091/181)
    are always included — they are never filtered out.
    Never raises.
    """
    if _client:
        try:
            return fetch_with_fallback(
                _client, path="", source="Emergency API",
                fallback_loader=lambda: _load_emergency_from_db(db),
                params={"category": "emergency", "location": "Pune"},
            )
        except Exception:
            logger.exception("Unexpected error in emergency live fetch; using DB fallback")
    return _load_emergency_from_db(db)


def get_all_emergency_resources(db: Session) -> list[dict[str, Any]]:
    return get_emergency_resources(db)


def describe_emergency_sources() -> dict[str, Any]:
    return {
        "live_api_configured": bool(_EMERGENCY_API_URL),
        "live_api_url": _EMERGENCY_API_URL or None,
        "fallback": "PostgreSQL verified data",
        "categories_served": [EMERGENCY_CATEGORY],
        "critical_helplines": [
            {"name": "Police Emergency", "contact": "100"},
            {"name": "National Emergency Number", "contact": "112"},
            {"name": "Women Helpline", "contact": "1091"},
            {"name": "National Women Helpline", "contact": "181"},
            {"name": "Ambulance", "contact": "108"},
        ],
        "safety_note": (
            "For any life-threatening emergency call 100 (Police) or 112 immediately. "
            "This service provides verified emergency resource information only. "
            "SakhiPune AI does not directly provide emergency assistance."
        ),
        "verified_resources": [
            {"name": "Police Emergency Helpline",        "source": "Pune Police — contact 100"},
            {"name": "Women Helpline 1091",              "source": "Pune Police — contact 1091"},
            {"name": "National Emergency Ambulance",     "source": "Government of India — contact 108"},
            {"name": "Pune Police Bharosa Cell",         "source": "Pune Police — contact 1091"},
            {"name": "National Women Helpline 181",      "source": "WCD Ministry — contact 181"},
        ],
        "note": (
            "Emergency helplines are verified government numbers. "
            "No additional public API is required — these are static official contacts. "
            "Set EMERGENCY_API_URL in .env if a supplementary live source becomes available."
        ),
    }
