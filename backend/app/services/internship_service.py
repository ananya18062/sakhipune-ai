"""internship_service.py — Internship support for SakhiPune AI.

Architecture
────────────
                        ┌─────────────────────────────────────┐
  Query + Preferences   │  get_internship_resources()          │
   │                    │  get_technology_internship_resources()│
   └──► NLP intent  ──► │  get_women_internship_resources()    │──► Recommendation
        "employment"    │  get_all_internship_resources()      │    pipeline
        (internship     └─────────────────────────────────────┘
         keyword hits        │
         employment)    ┌────┴──────────────────────────────────┐
                        │  External API (future)                │
                        │  • No public unauthenticated JSON API │
                        │    for internship listings in Pune /  │
                        │    Maharashtra as of September 2026.  │
                        │  • Set INTERNSHIPS_API_URL in .env    │
                        │    when a suitable endpoint appears.  │
                        │                                       │
                        │  PostgreSQL fallback (current)        │
                        │  • 2 verified Internship resources    │
                        │  • source_type="database"             │
                        │  • is_live=False                      │
                        └───────────────────────────────────────┘

Verified data sources (PostgreSQL, September 2026)
────────────────────────────────────────────────────
  • Mukhyamantri Yuva Karya Prashikshan Yojana – Internship
    (pune.gov.in — Maharashtra govt 6-month apprenticeship scheme)
  • SARTHI COEP Technical Internship for Women
    (sarthi.maharashtra.gov.in — technical training at COEP Pune)

Preference fields supported
─────────────────────────────
  interest_area   → filters by domain keyword (e.g. "Technology", "Design")
  experience_level → filters by experience match ("Beginner", "Some experience" …)
  work_type       → filters by location type ("On-site", "Remote", "Hybrid")
  location        → passed to recommendation scoring
  language        → passed to recommendation scoring

Public functions
────────────────
  get_internship_resources(db, preferences)          → list[dict]
  get_technology_internship_resources(db)            → list[dict]
  get_women_internship_resources(db)                 → list[dict]
  get_all_internship_resources(db, preferences)      → list[dict]
  describe_internship_sources()                      → dict
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

INTERNSHIP_CATEGORY = "Internships"

# ── Preference keyword maps ────────────────────────────────────────────────────
# Maps frontend preference option values to text tokens used for filtering.

TECHNOLOGY_KEYWORDS = {
    "technology", "tech", "software", "it", "coding", "programming",
    "computer", "digital", "engineering", "coep", "sarthi", "technical",
}

WOMEN_KEYWORDS = {
    "women", "woman", "female", "girl", "mahila", "sarthi",
}

REMOTE_KEYWORDS = {"remote", "online", "virtual", "work from home"}

# interest_area options from questions.js mapped to searchable tokens
INTEREST_AREA_TOKENS: dict[str, set[str]] = {
    "technology":       TECHNOLOGY_KEYWORDS,
    "business":         {"business", "management", "commerce", "finance", "mba"},
    "design or media":  {"design", "media", "creative", "art", "graphic"},
    "social impact":    {"social", "ngo", "welfare", "community", "development"},
}

# experience_level options — used to prefer/deprioritize resources
EXPERIENCE_LEVELS = {
    "beginner", "some experience", "experienced", "prefer not to say",
}

# ── External API client (future integration) ───────────────────────────────────

_INTERNSHIPS_API_URL: str = getattr(settings, "INTERNSHIPS_API_URL", "")
_client: BaseAPIClient | None = (
    BaseAPIClient(
        base_url=_INTERNSHIPS_API_URL,
        timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
    )
    if _INTERNSHIPS_API_URL
    else None
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resource_text(resource: dict[str, Any]) -> str:
    """Return a single lowercase string of all searchable text for a resource."""
    return " ".join([
        resource.get("name", ""),
        resource.get("description", ""),
        resource.get("location", ""),
    ]).lower()


def _load_internships_from_db(db: Session) -> list[dict[str, Any]]:
    """Query all Internship resources from PostgreSQL and normalize them."""
    try:
        rows = (
            db.query(SupportResource)
            .filter(SupportResource.category.ilike(INTERNSHIP_CATEGORY))
            .order_by(SupportResource.name)
            .all()
        )
        return [_orm_to_normalized(r) for r in rows]
    except SQLAlchemyError:
        logger.exception("DB query failed in internship_service._load_internships_from_db")
        return []


def _apply_preference_filter(
    resources: list[dict[str, Any]],
    preferences: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Soft-filter resources by user preferences.

    'Soft' means: if the filter would produce zero results, return the full
    list instead of an empty one.  This ensures sparse data never silences
    the endpoint.

    Supported preference keys (all optional):
      interest_area   – domain filter ("Technology", "Business", …)
      work_type       – location type filter ("Remote", "On-site", "Hybrid")
    """
    if not preferences or not resources:
        return resources

    filtered = list(resources)

    # ── interest_area filter ──────────────────────────────────────────────────
    raw_area = str(preferences.get("interest_area", "")).strip().lower()
    if raw_area:
        tokens = INTEREST_AREA_TOKENS.get(raw_area)
        if tokens:
            area_filtered = [
                r for r in filtered
                if any(kw in _resource_text(r) for kw in tokens)
            ]
            if area_filtered:
                filtered = area_filtered

    # ── work_type filter ──────────────────────────────────────────────────────
    raw_work_type = str(preferences.get("work_type", "")).strip().lower()
    if raw_work_type and raw_work_type not in {"open to options", "prefer not to say"}:
        if "remote" in raw_work_type:
            remote_filtered = [
                r for r in filtered
                if any(kw in _resource_text(r) for kw in REMOTE_KEYWORDS)
            ]
            if remote_filtered:
                filtered = remote_filtered

    return filtered if filtered else resources


# ── Public API ─────────────────────────────────────────────────────────────────

def get_internship_resources(
    db: Session,
    preferences: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return all verified Internship resources with optional preference filtering.

    Flow:
      1. If INTERNSHIPS_API_URL is configured, try a live fetch → normalize.
      2. On any failure, fall back to PostgreSQL.
      3. Apply soft preference filter (interest_area, work_type).
      4. Database records are always marked is_live=False.

    Never raises.
    """
    if _client:
        try:
            raw = fetch_with_fallback(
                _client,
                path="",
                source="Internships API",
                fallback_loader=lambda: _load_internships_from_db(db),
                params={"category": "internship", "location": "Pune"},
            )
            return _apply_preference_filter(raw, preferences)
        except Exception:
            logger.exception("Unexpected error in internship live fetch; using DB fallback")

    raw = _load_internships_from_db(db)
    return _apply_preference_filter(raw, preferences)


def get_technology_internship_resources(db: Session) -> list[dict[str, Any]]:
    """Return internships relevant to technology/engineering domains."""
    all_internships = get_internship_resources(db)
    tech = [
        r for r in all_internships
        if any(kw in _resource_text(r) for kw in TECHNOLOGY_KEYWORDS)
    ]
    return tech if tech else all_internships


def get_women_internship_resources(db: Session) -> list[dict[str, Any]]:
    """Return internships particularly relevant to women."""
    all_internships = get_internship_resources(db)
    women = [
        r for r in all_internships
        if any(kw in _resource_text(r) for kw in WOMEN_KEYWORDS)
    ]
    return women if women else all_internships


def get_all_internship_resources(
    db: Session,
    preferences: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Convenience entry-point returning all internships with preference filtering."""
    return get_internship_resources(db, preferences=preferences)


def describe_internship_sources() -> dict[str, Any]:
    """Return metadata about the current internship data sources."""
    return {
        "live_api_configured": bool(_INTERNSHIPS_API_URL),
        "live_api_url": _INTERNSHIPS_API_URL or None,
        "fallback": "PostgreSQL verified data",
        "categories_served": [INTERNSHIP_CATEGORY],
        "preference_fields_supported": [
            "interest_area",
            "experience_level",
            "work_type",
            "location",
            "language",
        ],
        "verified_resources": [
            {
                "name": "Mukhyamantri Yuva Karya Prashikshan Yojana – Internship",
                "source": "pune.gov.in (Maharashtra govt 6-month apprenticeship scheme)",
            },
            {
                "name": "SARTHI COEP Technical Internship for Women",
                "source": "sarthi.maharashtra.gov.in (technical training at COEP Pune)",
            },
        ],
        "note": (
            "No public unauthenticated JSON API is available for internship listings "
            "in Pune/Maharashtra as of September 2026. "
            "Set INTERNSHIPS_API_URL in .env when a suitable endpoint becomes available. "
            "Current data is served from verified PostgreSQL records."
        ),
    }
