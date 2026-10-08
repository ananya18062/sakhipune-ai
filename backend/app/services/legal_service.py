"""legal_service.py — Legal Support for SakhiPune AI.

Architecture
────────────
                        ┌──────────────────────────────────────┐
  Query                 │  get_legal_resources()                │
   │                    │  get_domestic_violence_legal_         │
   └──► NLP intent  ──► │    resources()                       │──► Recommendation
        "legal"         │  get_women_legal_resources()          │    pipeline
        "domestic_      │  get_all_legal_resources()            │
         violence"      └──────────────────────────────────────┘
                                       │
               ┌───────────────────────┴─────────────────────┐
               │  External API (future)                      │
               │  • No public unauthenticated JSON API for   │
               │    legal services in Pune/Maharashtra as of │
               │    September 2026. DLSA and MSLSA portals   │
               │    are web-only.                            │
               │  • Set LEGAL_API_URL in .env when a         │
               │    suitable endpoint becomes available.     │
               │                                             │
               │  PostgreSQL fallback (current)              │
               │  • 5 verified Legal Support resources       │
               │  • source_type="database", is_live=False    │
               └─────────────────────────────────────────────┘

Verified data sources (PostgreSQL, September 2026)
────────────────────────────────────────────────────
  • Pune District Legal Services Authority (DLSA) — punedlsa.org
  • Maharashtra State Legal Services Authority (MSLSA) — legalservices.maharashtra.gov.in
  • Sakhi One Stop Centre (OSC) — 181
  • Bombay High Court Legal Aid Committee — bombayhighcourt.gov.in
  • Protection Officer – Domestic Violence Act — womenchild.maharashtra.gov.in

IMPORTANT:
  This service returns information about legal support resources only.
  It does not provide legal advice, legal opinions or represent any party.

Public functions
────────────────
  get_legal_resources(db)                    → list[dict]  (all Legal Support)
  get_domestic_violence_legal_resources(db)  → list[dict]  (DV-specific subset)
  get_women_legal_resources(db)              → list[dict]  (women-focused subset)
  get_all_legal_resources(db)                → list[dict]  (convenience alias)
  describe_legal_sources()                   → dict        (operator metadata)
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

# ── Category constant ─────────────────────────────────────────────────────────

LEGAL_CATEGORY = "Legal Support"

# ── Keyword sets for sub-filtering ────────────────────────────────────────────

DOMESTIC_VIOLENCE_KEYWORDS = {
    "domestic", "violence", "abuse", "protection", "dv act",
    "domestic violence", "protection officer", "incident report",
    "sakhi", "one stop", "osc",
}

WOMEN_LEGAL_KEYWORDS = {
    "women", "woman", "female", "girl", "mahila",
    "domestic", "protection", "maintenance", "custody",
    "family law", "harassment", "dowry",
}

# ── External API client ───────────────────────────────────────────────────────

_LEGAL_API_URL: str = getattr(settings, "LEGAL_API_URL", "")
_client: BaseAPIClient | None = (
    BaseAPIClient(
        base_url=_LEGAL_API_URL,
        timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
    )
    if _LEGAL_API_URL
    else None
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resource_text(resource: dict[str, Any]) -> str:
    return " ".join([
        resource.get("name", ""),
        resource.get("description", ""),
        resource.get("location", ""),
    ]).lower()


def _load_legal_from_db(db: Session) -> list[dict[str, Any]]:
    """Query all Legal Support resources from PostgreSQL and normalize them."""
    try:
        rows = (
            db.query(SupportResource)
            .filter(SupportResource.category.ilike(LEGAL_CATEGORY))
            .order_by(SupportResource.name)
            .all()
        )
        return [_orm_to_normalized(r) for r in rows]
    except SQLAlchemyError:
        logger.exception("DB query failed in legal_service._load_legal_from_db")
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def get_legal_resources(db: Session) -> list[dict[str, Any]]:
    """Return all verified Legal Support resources, normalized to the common format.

    Flow:
      1. If LEGAL_API_URL is configured, try a live fetch → normalize.
      2. On any failure, fall back to PostgreSQL.
      3. Database records are always marked is_live=False.

    Never raises.
    """
    if _client:
        try:
            return fetch_with_fallback(
                _client,
                path="",
                source="Legal API",
                fallback_loader=lambda: _load_legal_from_db(db),
                params={"category": "legal", "state": "Maharashtra"},
            )
        except Exception:
            logger.exception("Unexpected error in legal live fetch; using DB fallback")

    return _load_legal_from_db(db)


def get_domestic_violence_legal_resources(db: Session) -> list[dict[str, Any]]:
    """Return legal resources specifically relevant to domestic violence cases.

    Falls back to the full legal list if no DV-specific resources are found.
    """
    all_legal = get_legal_resources(db)
    dv = [
        r for r in all_legal
        if any(kw in _resource_text(r) for kw in DOMESTIC_VIOLENCE_KEYWORDS)
    ]
    return dv if dv else all_legal


def get_women_legal_resources(db: Session) -> list[dict[str, Any]]:
    """Return legal resources particularly relevant to women.

    Falls back to the full legal list if no women-specific resources are found.
    """
    all_legal = get_legal_resources(db)
    women = [
        r for r in all_legal
        if any(kw in _resource_text(r) for kw in WOMEN_LEGAL_KEYWORDS)
    ]
    return women if women else all_legal


def get_all_legal_resources(db: Session) -> list[dict[str, Any]]:
    """Convenience alias for get_legal_resources()."""
    return get_legal_resources(db)


def describe_legal_sources() -> dict[str, Any]:
    """Return metadata about the current legal data sources."""
    return {
        "live_api_configured": bool(_LEGAL_API_URL),
        "live_api_url": _LEGAL_API_URL or None,
        "fallback": "PostgreSQL verified data",
        "categories_served": [LEGAL_CATEGORY],
        "verified_resources": [
            {
                "name": "Pune District Legal Services Authority (DLSA)",
                "source": "punedlsa.org (District Court, Pune)",
            },
            {
                "name": "Maharashtra State Legal Services Authority (MSLSA)",
                "source": "legalservices.maharashtra.gov.in (Maharashtra Government)",
            },
            {
                "name": "Sakhi One Stop Centre (OSC)",
                "source": "WCD Ministry — contact via 181",
            },
            {
                "name": "Bombay High Court Legal Aid Committee",
                "source": "bombayhighcourt.gov.in",
            },
            {
                "name": "Protection Officer – Domestic Violence Act",
                "source": "womenchild.maharashtra.gov.in (Maharashtra WCD)",
            },
        ],
        "disclaimer": (
            "This service provides information about legal support resources only. "
            "It does not provide legal advice, legal opinions or represent any party."
        ),
        "note": (
            "No public unauthenticated JSON API is available for legal services "
            "in Pune/Maharashtra as of September 2026. "
            "DLSA and MSLSA portals are web-only without open JSON endpoints. "
            "Set LEGAL_API_URL in .env when a suitable endpoint becomes available. "
            "Current data is served from verified PostgreSQL records."
        ),
    }
