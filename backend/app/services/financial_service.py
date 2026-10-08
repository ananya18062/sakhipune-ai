"""financial_service.py — Financial Support for SakhiPune AI.

Architecture
────────────
                        ┌──────────────────────────────────────┐
  Query                 │  get_financial_resources()            │
   │                    │  get_women_financial_resources()      │
   └──► NLP intent  ──► │  get_livelihood_resources()           │──► Recommendation
        "financial_     │  get_all_financial_resources()        │    pipeline
         support"       └──────────────────────────────────────┘
                                       │
               ┌───────────────────────┴─────────────────────┐
               │  External API (future)                      │
               │  • No public unauthenticated JSON API for   │
               │    financial schemes in Pune/Maharashtra as │
               │    of September 2026.  MAVIM, NULM and      │
               │    Jan Dhan portals are web-only.           │
               │  • Set FINANCIAL_API_URL in .env when a     │
               │    suitable endpoint becomes available.     │
               │                                             │
               │  PostgreSQL fallback (current)              │
               │  • 4 verified Financial Support resources   │
               │  • source_type="database", is_live=False    │
               └─────────────────────────────────────────────┘

Verified data sources (PostgreSQL, September 2026)
────────────────────────────────────────────────────
  • Mahila Arthik Vikas Mahamandal (MAVIM)      — mavim.maharashtra.gov.in
  • DAY-NULM Micro-credit Support               — pmc.gov.in
  • PM Jan Dhan Yojana – Women's Bank Account   — pmjdy.gov.in
  • Mukhyamantri Majhi Ladki Bahin – Financial Aid — ladakibahin.maharashtra.gov.in

Public functions
────────────────
  get_financial_resources(db)         → list[dict]  (all Financial Support)
  get_women_financial_resources(db)   → list[dict]  (women-specific subset)
  get_livelihood_resources(db)        → list[dict]  (livelihood/micro-credit subset)
  get_all_financial_resources(db)     → list[dict]  (convenience alias)
  describe_financial_sources()        → dict        (operator metadata)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.models import SupportResource
from app.services.api_clients.base_client import (
    BaseAPIClient,
    fetch_with_fallback,
    normalize_resource,
)
from app.services.resource_normalizer import orm_to_normalized as _orm_to_normalized
from app.core.config import settings

logger = logging.getLogger(__name__)

FINANCIAL_CATEGORY = "Financial Support"

WOMEN_FINANCIAL_KEYWORDS = {
    "women", "woman", "female", "girl", "mahila",
    "ladki", "bahin", "mavim",
}

LIVELIHOOD_KEYWORDS = {
    "livelihood", "micro", "credit", "loan", "shg", "self-help",
    "nulm", "microfinance", "income", "business", "enterprise",
}

_FINANCIAL_API_URL: str = getattr(settings, "FINANCIAL_API_URL", "")
_client: BaseAPIClient | None = (
    BaseAPIClient(base_url=_FINANCIAL_API_URL, timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS)
    if _FINANCIAL_API_URL else None
)


def _resource_text(resource: dict[str, Any]) -> str:
    return " ".join([
        resource.get("name", ""),
        resource.get("description", ""),
        resource.get("location", ""),
    ]).lower()


def _load_financial_from_db(db: Session) -> list[dict[str, Any]]:
    try:
        rows = (
            db.query(SupportResource)
            .filter(SupportResource.category.ilike(FINANCIAL_CATEGORY))
            .order_by(SupportResource.name)
            .all()
        )
        return [_orm_to_normalized(r) for r in rows]
    except SQLAlchemyError:
        logger.exception("DB query failed in financial_service._load_financial_from_db")
        return []


def get_financial_resources(db: Session) -> list[dict[str, Any]]:
    """Return all verified Financial Support resources normalized to the common format.

    Falls back to PostgreSQL when FINANCIAL_API_URL is not configured or fails.
    Never raises.
    """
    if _client:
        try:
            return fetch_with_fallback(
                _client,
                path="",
                source="Financial API",
                fallback_loader=lambda: _load_financial_from_db(db),
                params={"category": "financial", "state": "Maharashtra"},
            )
        except Exception:
            logger.exception("Unexpected error in financial live fetch; using DB fallback")
    return _load_financial_from_db(db)


def get_women_financial_resources(db: Session) -> list[dict[str, Any]]:
    """Return financial resources specifically relevant to women.

    Falls back to the full list when no women-specific resources are found.
    """
    all_fin = get_financial_resources(db)
    women = [
        r for r in all_fin
        if any(kw in _resource_text(r) for kw in WOMEN_FINANCIAL_KEYWORDS)
    ]
    return women if women else all_fin


def get_livelihood_resources(db: Session) -> list[dict[str, Any]]:
    """Return livelihood and micro-credit focused financial resources.

    Falls back to the full list when no livelihood-specific resources are found.
    """
    all_fin = get_financial_resources(db)
    livelihood = [
        r for r in all_fin
        if any(kw in _resource_text(r) for kw in LIVELIHOOD_KEYWORDS)
    ]
    return livelihood if livelihood else all_fin


def get_all_financial_resources(db: Session) -> list[dict[str, Any]]:
    """Convenience alias for get_financial_resources()."""
    return get_financial_resources(db)


def describe_financial_sources() -> dict[str, Any]:
    """Return metadata about the current financial data sources."""
    return {
        "live_api_configured": bool(_FINANCIAL_API_URL),
        "live_api_url": _FINANCIAL_API_URL or None,
        "fallback": "PostgreSQL verified data",
        "categories_served": [FINANCIAL_CATEGORY],
        "verified_resources": [
            {
                "name": "Mahila Arthik Vikas Mahamandal (MAVIM)",
                "source": "mavim.maharashtra.gov.in (Maharashtra Government)",
            },
            {
                "name": "DAY-NULM Micro-credit Support",
                "source": "pmc.gov.in (Pune Municipal Corporation)",
            },
            {
                "name": "PM Jan Dhan Yojana – Women's Bank Account",
                "source": "pmjdy.gov.in (Government of India)",
            },
            {
                "name": "Mukhyamantri Majhi Ladki Bahin – Financial Aid",
                "source": "ladakibahin.maharashtra.gov.in (Maharashtra Government)",
            },
        ],
        "note": (
            "No public unauthenticated JSON API is available for financial support "
            "schemes in Pune/Maharashtra as of September 2026. "
            "MAVIM, NULM and Jan Dhan portals are web-only without open JSON endpoints. "
            "Set FINANCIAL_API_URL in .env when a suitable endpoint becomes available. "
            "Current data is served from verified PostgreSQL records."
        ),
    }
