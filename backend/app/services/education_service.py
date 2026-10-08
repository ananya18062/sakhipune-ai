"""education_service.py — Education and Scholarship support for SakhiPune AI.

Architecture
────────────
                        ┌─────────────────────────────┐
  Query                 │  get_education_resources()   │
   │                    │  get_scholarship_resources() │
   └──► NLP intent  ──► │  get_education_and_          │ ──► Recommendation
        "education"     │    scholarship_resources()   │     pipeline
                        └─────────────────────────────┘
                                    │
               ┌────────────────────┴────────────────────┐
               │  External API (future)                  │
               │  • No public JSON API exists for NSP    │
               │    or MahaDbt without institutional     │
               │    credentials (confirmed September     │
               │    2026 research).                      │
               │  • BaseAPIClient is wired and ready;    │
               │    set EDUCATION_API_URL in .env when   │
               │    an endpoint becomes available.       │
               │                                         │
               │  PostgreSQL fallback (current)          │
               │  • 5 verified Education resources       │
               │  • source_type="database", is_live=False│
               └─────────────────────────────────────────┘

Public functions
────────────────
  get_education_resources(db)        → list[dict]  (Education category)
  get_scholarship_resources(db)      → list[dict]  (scholarship-focused subset)
  get_education_and_scholarship_resources(db)
                                     → list[dict]  (merged, deduplicated)

All functions return the common NormalizedResource dict format so results
slot directly into the existing recommendation pipeline without changes to
recommendation_service.py or routes.py.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.models import SupportResource
from app.services.api_clients.base_client import (
    BaseAPIClient,
    ExternalAPIError,
    fetch_with_fallback,
    normalize_resource,
)
from app.services.resource_normalizer import orm_to_normalized as _orm_to_normalized
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Category constants ────────────────────────────────────────────────────────

EDUCATION_CATEGORY = "Education"

# Keywords that identify scholarship-focused resources within the Education
# category.  Used by get_scholarship_resources() to filter the DB results.
SCHOLARSHIP_KEYWORDS = {
    "scholarship", "scholarships", "financial aid", "stipend",
    "grant", "fee waiver", "mahadbt", "savitribai", "foreign scholarship",
    "minority", "sc", "st", "obc", "vjnt", "sbc",
}

# ── External API client (future integration) ──────────────────────────────────
# No public unauthenticated endpoint is available for NSP / MahaDbt as of
# September 2026.  The client is constructed here so that when an endpoint
# becomes available, only EDUCATION_API_URL needs to be added to .env.

_EDUCATION_API_URL: str = getattr(settings, "EDUCATION_API_URL", "")
_client: BaseAPIClient | None = (
    BaseAPIClient(base_url=_EDUCATION_API_URL, timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS)
    if _EDUCATION_API_URL
    else None
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_scholarship_resource(resource: SupportResource) -> bool:
    """Return True if this Education resource is scholarship-focused."""
    text = " ".join([
        resource.name or "",
        resource.description or "",
        resource.keywords or "",
    ]).lower()
    return any(kw in text for kw in SCHOLARSHIP_KEYWORDS)


def _load_education_from_db(db: Session) -> list[dict[str, Any]]:
    """Query all Education resources from PostgreSQL and normalize them."""
    try:
        rows = (
            db.query(SupportResource)
            .filter(SupportResource.category.ilike(EDUCATION_CATEGORY))
            .order_by(SupportResource.name)
            .all()
        )
        return [_orm_to_normalized(r) for r in rows]
    except SQLAlchemyError:
        logger.exception("Database query failed in education_service._load_education_from_db")
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def get_education_resources(db: Session) -> list[dict[str, Any]]:
    """Return all verified Education resources, normalized to the common format.

    Flow:
      1. If EDUCATION_API_URL is configured, try live fetch → normalize.
      2. On any failure, or if no URL is configured, fall back to PostgreSQL.
      3. Database results are always marked is_live=False.

    Never raises — failures are logged and an empty list is returned rather
    than crashing the recommendation pipeline.
    """
    if _client:
        try:
            return fetch_with_fallback(
                _client,
                path="",
                source="Education API",
                fallback_loader=lambda: _load_education_from_db(db),
                params={"category": "education", "state": "Maharashtra"},
            )
        except Exception:
            logger.exception("Unexpected error in education fetch; using DB fallback")

    return _load_education_from_db(db)


def get_scholarship_resources(db: Session) -> list[dict[str, Any]]:
    """Return scholarship-focused Education resources only.

    Filters the full Education list to entries whose name/description/keywords
    contain scholarship-related terms.  Falls back to the full Education list
    if no scholarship-specific resources are found.
    """
    all_education = get_education_resources(db)
    scholarships = [
        r for r in all_education
        if any(kw in (r.get("name", "") + r.get("description", "")).lower()
               for kw in SCHOLARSHIP_KEYWORDS)
    ]
    # If the filter produces nothing (unlikely with current data) return all
    return scholarships if scholarships else all_education


def get_education_and_scholarship_resources(db: Session) -> list[dict[str, Any]]:
    """Return the merged, deduplicated Education + Scholarship resource list.

    Since all scholarship resources are a subset of Education resources, this
    simply returns the full Education list (no duplication can occur).
    Provided as a single convenience entry-point for routes that want both.
    """
    return get_education_resources(db)


def describe_education_sources() -> dict[str, Any]:
    """Return metadata about the current education data sources.

    Used by /education/sources endpoint so operators can verify what data is
    being served and whether a live API is active.
    """
    return {
        "live_api_configured": bool(_EDUCATION_API_URL),
        "live_api_url": _EDUCATION_API_URL or None,
        "fallback": "PostgreSQL verified data",
        "categories_served": [EDUCATION_CATEGORY],
        "note": (
            "No public unauthenticated JSON API is available for NSP or MahaDbt "
            "as of September 2026. Set EDUCATION_API_URL in .env when an endpoint "
            "becomes available. Current data is served from verified PostgreSQL records."
        ),
    }
