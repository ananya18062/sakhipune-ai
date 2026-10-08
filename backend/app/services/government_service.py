"""government_service.py — Government Schemes support for SakhiPune AI.

Verified data sources (PostgreSQL, September 2026)
────────────────────────────────────────────────────
  • Mukhyamantri Majhi Ladki Bahin Yojana  — pune.gov.in
  • PM Ujjwala Yojana                       — pmujjwalayojana.com
  • Manodhairya Scheme – Maharashtra WCD    — womenchild.maharashtra.gov.in
  • Swadhar Greh Scheme – Ministry of WCD   — wcd.gov.in
  • PM Matru Vandana Yojana (PMMVY)         — pmmvy-cas.nic.in
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
GOVERNMENT_CATEGORY = "Government Schemes"

_GOVERNMENT_API_URL: str = getattr(settings, "GOVERNMENT_API_URL", "")
_client: BaseAPIClient | None = (
    BaseAPIClient(base_url=_GOVERNMENT_API_URL, timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS)
    if _GOVERNMENT_API_URL else None
)


def _load_government_from_db(db: Session) -> list[dict[str, Any]]:
    try:
        rows = (db.query(SupportResource)
                .filter(SupportResource.category.ilike(GOVERNMENT_CATEGORY))
                .order_by(SupportResource.name).all())
        return [_orm_to_normalized(r) for r in rows]
    except SQLAlchemyError:
        logger.exception("DB query failed in government_service")
        return []


def get_government_resources(db: Session) -> list[dict[str, Any]]:
    """Return all verified Government Scheme resources. Never raises."""
    if _client:
        try:
            return fetch_with_fallback(
                _client, path="", source="Government API",
                fallback_loader=lambda: _load_government_from_db(db),
                params={"category": "government_scheme", "state": "Maharashtra"},
            )
        except Exception:
            logger.exception("Unexpected error in government live fetch; using DB fallback")
    return _load_government_from_db(db)


def get_all_government_resources(db: Session) -> list[dict[str, Any]]:
    return get_government_resources(db)


def describe_government_sources() -> dict[str, Any]:
    return {
        "live_api_configured": bool(_GOVERNMENT_API_URL),
        "live_api_url": _GOVERNMENT_API_URL or None,
        "fallback": "PostgreSQL verified data",
        "categories_served": [GOVERNMENT_CATEGORY],
        "verified_resources": [
            {"name": "Mukhyamantri Majhi Ladki Bahin Yojana",
             "source": "pune.gov.in (Maharashtra Government)"},
            {"name": "PM Ujjwala Yojana",
             "source": "pmujjwalayojana.com (Government of India)"},
            {"name": "Manodhairya Scheme – Maharashtra WCD",
             "source": "womenchild.maharashtra.gov.in (Maharashtra WCD)"},
            {"name": "Swadhar Greh Scheme – Ministry of WCD",
             "source": "wcd.gov.in (Ministry of WCD, Government of India)"},
            {"name": "PM Matru Vandana Yojana (PMMVY)",
             "source": "pmmvy-cas.nic.in (Government of India)"},
        ],
        "note": (
            "No public unauthenticated JSON API exists for government scheme listings "
            "in Pune/Maharashtra as of September 2026. "
            "Set GOVERNMENT_API_URL in .env when available. "
            "Current data is served from verified PostgreSQL records."
        ),
    }
