"""shelter_service.py — Shelter support for SakhiPune AI.

Verified data sources (PostgreSQL, September 2026)
────────────────────────────────────────────────────
  • Swadhar Greh Shelter Home (WCD Scheme)          — 181
  • Sakhi One Stop Centre – Emergency Shelter        — 181
  • Pune Police Bharosa Cell – Safe Referral         — 1091

SAFETY NOTE:
  This service returns information about shelter resources only.
  Women in immediate danger should call 100 (Police) or 112 (Emergency).
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
SHELTER_CATEGORY = "Shelters"

EMERGENCY_SHELTER_KEYWORDS = {
    "emergency", "immediate", "urgent", "sakhi", "osc", "one stop",
}
WOMEN_SHELTER_KEYWORDS = {
    "women", "woman", "female", "girl", "mahila",
    "swadhar", "sakhi", "bharosa", "domestic",
}

_SHELTER_API_URL: str = getattr(settings, "SHELTER_API_URL", "")
_client: BaseAPIClient | None = (
    BaseAPIClient(base_url=_SHELTER_API_URL, timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS)
    if _SHELTER_API_URL else None
)


def _resource_text(r: dict[str, Any]) -> str:
    return " ".join([r.get("name",""), r.get("description",""), r.get("location","")]).lower()


def _load_shelters_from_db(db: Session) -> list[dict[str, Any]]:
    try:
        rows = (db.query(SupportResource)
                .filter(SupportResource.category.ilike(SHELTER_CATEGORY))
                .order_by(SupportResource.name).all())
        return [_orm_to_normalized(r) for r in rows]
    except SQLAlchemyError:
        logger.exception("DB query failed in shelter_service")
        return []


def get_shelter_resources(db: Session) -> list[dict[str, Any]]:
    """Return all verified Shelter resources. Never raises."""
    if _client:
        try:
            return fetch_with_fallback(
                _client, path="", source="Shelter API",
                fallback_loader=lambda: _load_shelters_from_db(db),
                params={"category": "shelter", "location": "Pune"},
            )
        except Exception:
            logger.exception("Unexpected error in shelter live fetch; using DB fallback")
    return _load_shelters_from_db(db)


def get_emergency_shelter_resources(db: Session) -> list[dict[str, Any]]:
    """Return shelter resources with emergency/immediate availability.
    Falls back to full list if no emergency-specific shelters found."""
    all_s = get_shelter_resources(db)
    emerg = [r for r in all_s if any(kw in _resource_text(r) for kw in EMERGENCY_SHELTER_KEYWORDS)]
    return emerg if emerg else all_s


def get_all_shelter_resources(db: Session) -> list[dict[str, Any]]:
    return get_shelter_resources(db)


def describe_shelter_sources() -> dict[str, Any]:
    return {
        "live_api_configured": bool(_SHELTER_API_URL),
        "live_api_url": _SHELTER_API_URL or None,
        "fallback": "PostgreSQL verified data",
        "categories_served": [SHELTER_CATEGORY],
        "verified_resources": [
            {"name": "Swadhar Greh Shelter Home (WCD Scheme)", "source": "WCD Ministry — contact 181"},
            {"name": "Sakhi One Stop Centre – Emergency Shelter", "source": "WCD Ministry — contact 181"},
            {"name": "Pune Police Bharosa Cell – Safe Referral", "source": "Pune Police — contact 1091"},
        ],
        "safety_note": (
            "Women in immediate danger should call 100 (Police) or 112 (Emergency). "
            "This service provides shelter resource information only."
        ),
        "note": (
            "No public unauthenticated JSON API exists for shelter listings in Pune/Maharashtra "
            "as of September 2026. Set SHELTER_API_URL in .env when available. "
            "Current data is served from verified PostgreSQL records."
        ),
    }
