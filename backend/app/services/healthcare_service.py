"""healthcare_service.py — Healthcare support for SakhiPune AI.

Architecture
────────────
                        ┌──────────────────────────────────────┐
  Query                 │  get_healthcare_resources()           │
   │                    │  get_maternal_healthcare_resources()  │
   └──► NLP intent  ──► │  get_women_healthcare_resources()    │──► Recommendation
        "healthcare"    │  get_all_healthcare_resources()       │    pipeline
                        └──────────────────────────────────────┘
                                      │
               ┌──────────────────────┴──────────────────────┐
               │  External API (future)                      │
               │  • No public unauthenticated JSON API for   │
               │    healthcare facilities in Pune/           │
               │    Maharashtra as of September 2026.        │
               │  • NHM, PMC and PMMVY portals are          │
               │    web-only without open JSON endpoints.    │
               │  • Set HEALTHCARE_API_URL in .env when a   │
               │    suitable endpoint becomes available.     │
               │                                             │
               │  PostgreSQL fallback (current)              │
               │  • 4 verified Healthcare resources          │
               │  • source_type="database", is_live=False    │
               └─────────────────────────────────────────────┘

Verified data sources (PostgreSQL, September 2026)
────────────────────────────────────────────────────
  • Sassoon General Hospital (B.J. Medical College) — 020-26128000
  • National Health Mission – Janani Suraksha Yojana — nhm.gov.in
  • Pradhan Mantri Matru Vandana Yojana (PMMVY)     — pmmvy-cas.nic.in
  • Pune Municipal Corporation – Health Centres      — pmc.gov.in

Public functions
────────────────
  get_healthcare_resources(db)          → list[dict]  (all Healthcare)
  get_maternal_healthcare_resources(db) → list[dict]  (maternal/pregnancy subset)
  get_women_healthcare_resources(db)    → list[dict]  (women-focused subset)
  get_all_healthcare_resources(db)      → list[dict]  (convenience alias)
  describe_healthcare_sources()         → dict        (operator metadata)
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

HEALTHCARE_CATEGORY = "Healthcare"

# ── Keyword sets for sub-filtering ────────────────────────────────────────────

MATERNAL_KEYWORDS = {
    "maternal", "maternity", "pregnancy", "pregnant", "prenatal",
    "antenatal", "postnatal", "delivery", "janani", "pmmvy", "jsy",
    "mother", "infant", "newborn", "breastfeed", "lactating",
}

WOMEN_HEALTHCARE_KEYWORDS = {
    "women", "woman", "female", "girl", "mahila",
    "gynaecology", "gynecology", "obstetrics", "menstrual",
    "reproductive", "maternal", "maternity",
}

# ── External API client ───────────────────────────────────────────────────────

_HEALTHCARE_API_URL: str = getattr(settings, "HEALTHCARE_API_URL", "")
_client: BaseAPIClient | None = (
    BaseAPIClient(
        base_url=_HEALTHCARE_API_URL,
        timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
    )
    if _HEALTHCARE_API_URL
    else None
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resource_text(resource: dict[str, Any]) -> str:
    return " ".join([
        resource.get("name", ""),
        resource.get("description", ""),
        resource.get("location", ""),
    ]).lower()


def _load_healthcare_from_db(db: Session) -> list[dict[str, Any]]:
    """Query all Healthcare resources from PostgreSQL and normalize them."""
    try:
        rows = (
            db.query(SupportResource)
            .filter(SupportResource.category.ilike(HEALTHCARE_CATEGORY))
            .order_by(SupportResource.name)
            .all()
        )
        return [_orm_to_normalized(r) for r in rows]
    except SQLAlchemyError:
        logger.exception("DB query failed in healthcare_service._load_healthcare_from_db")
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def get_healthcare_resources(db: Session) -> list[dict[str, Any]]:
    """Return all verified Healthcare resources, normalized to the common format.

    Flow:
      1. If HEALTHCARE_API_URL is configured, try a live fetch → normalize.
      2. On any failure, fall back to PostgreSQL.
      3. Database records are always marked is_live=False.

    Never raises.
    """
    if _client:
        try:
            return fetch_with_fallback(
                _client,
                path="",
                source="Healthcare API",
                fallback_loader=lambda: _load_healthcare_from_db(db),
                params={"category": "healthcare", "location": "Pune", "state": "Maharashtra"},
            )
        except Exception:
            logger.exception("Unexpected error in healthcare live fetch; using DB fallback")

    return _load_healthcare_from_db(db)


def get_maternal_healthcare_resources(db: Session) -> list[dict[str, Any]]:
    """Return healthcare resources focused on maternal/pregnancy support.

    Falls back to the full list if no maternal resources are found.
    """
    all_hc = get_healthcare_resources(db)
    maternal = [
        r for r in all_hc
        if any(kw in _resource_text(r) for kw in MATERNAL_KEYWORDS)
    ]
    return maternal if maternal else all_hc


def get_women_healthcare_resources(db: Session) -> list[dict[str, Any]]:
    """Return healthcare resources particularly relevant to women.

    Falls back to the full list if no women-specific resources are found.
    """
    all_hc = get_healthcare_resources(db)
    women = [
        r for r in all_hc
        if any(kw in _resource_text(r) for kw in WOMEN_HEALTHCARE_KEYWORDS)
    ]
    return women if women else all_hc


def get_all_healthcare_resources(db: Session) -> list[dict[str, Any]]:
    """Convenience alias for get_healthcare_resources()."""
    return get_healthcare_resources(db)


def describe_healthcare_sources() -> dict[str, Any]:
    """Return metadata about the current healthcare data sources."""
    return {
        "live_api_configured": bool(_HEALTHCARE_API_URL),
        "live_api_url": _HEALTHCARE_API_URL or None,
        "fallback": "PostgreSQL verified data",
        "categories_served": [HEALTHCARE_CATEGORY],
        "verified_resources": [
            {
                "name": "Sassoon General Hospital (B.J. Medical College)",
                "source": "bjgmcpune.com / government hospital, Pune",
            },
            {
                "name": "National Health Mission – Janani Suraksha Yojana",
                "source": "nhm.gov.in (Government of India)",
            },
            {
                "name": "Pradhan Mantri Matru Vandana Yojana (PMMVY)",
                "source": "pmmvy-cas.nic.in (Government of India)",
            },
            {
                "name": "Pune Municipal Corporation – Health Centres",
                "source": "pmc.gov.in (Pune Municipal Corporation)",
            },
        ],
        "note": (
            "No public unauthenticated JSON API is available for healthcare "
            "facilities in Pune/Maharashtra as of September 2026. "
            "NHM, PMC and PMMVY portals are web-only without open JSON endpoints. "
            "Set HEALTHCARE_API_URL in .env when a suitable endpoint becomes available. "
            "Current data is served from verified PostgreSQL records."
        ),
    }
