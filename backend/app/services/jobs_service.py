"""jobs_service.py — Jobs and Employment support for SakhiPune AI.

Architecture
────────────
                        ┌──────────────────────────────┐
  Query                 │  get_job_resources()          │
   │                    │  get_women_job_resources()    │
   └──► NLP intent  ──► │  get_all_employment_          │ ──► Recommendation
        "employment"    │    resources()                │     pipeline
                        └──────────────────────────────┘
                                     │
               ┌─────────────────────┴─────────────────────┐
               │  External API (future)                    │
               │  • NCS (ncs.gov.in) — no public JSON API  │
               │    without employer/institutional login.  │
               │  • Mahaswayam — employer login required   │
               │    for vacancy data.                      │
               │  • data.gov.in — API key required,        │
               │    no real-time job listings endpoint.    │
               │  • Set JOBS_API_URL in .env when a        │
               │    suitable public endpoint is available. │
               │                                           │
               │  PostgreSQL fallback (current)            │
               │  • 4 verified Employment resources        │
               │  • source_type="database", is_live=False  │
               └───────────────────────────────────────────┘

Verified data sources (PostgreSQL, September 2026)
────────────────────────────────────────────────────
  • Mahaswayam Employment & Skill Guidance Centre   (mahaswayam.gov.in)
  • Mukhyamantri Yuva Karya Prashikshan Yojana      (pune.gov.in)
  • SARTHI Skill Development Programme for Women   (sarthi.maharashtra.gov.in)
  • DAY-NULM Self-Help Group Programme              (pmc.gov.in)

Public functions
────────────────
  get_job_resources(db)              → list[dict]  (all Employment resources)
  get_women_job_resources(db)        → list[dict]  (women-specific subset)
  get_all_employment_resources(db)   → list[dict]  (alias for get_job_resources)
  describe_job_sources()             → dict        (operator metadata)

All functions return the common NormalizedResource dict format.
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

# ── Category constant ─────────────────────────────────────────────────────────

EMPLOYMENT_CATEGORY = "Employment"

# Keywords that indicate a resource is particularly relevant to women
# seeking employment — used by get_women_job_resources() to filter results.
WOMEN_JOB_KEYWORDS = {
    "women", "woman", "female", "girl", "mahila",
    "skill", "sarthi", "nulm", "shg", "self-help",
}

# ── External API client (future integration) ──────────────────────────────────
# No public unauthenticated JSON API is available for NCS or Mahaswayam as
# of September 2026 (both require employer/institutional login).
# The client is wired and ready; set JOBS_API_URL in .env when an endpoint
# becomes available.

_JOBS_API_URL: str = getattr(settings, "JOBS_API_URL", "")
_client: BaseAPIClient | None = (
    BaseAPIClient(base_url=_JOBS_API_URL, timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS)
    if _JOBS_API_URL
    else None
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_jobs_from_db(db: Session) -> list[dict[str, Any]]:
    """Query all Employment resources from PostgreSQL and normalize them."""
    try:
        rows = (
            db.query(SupportResource)
            .filter(SupportResource.category.ilike(EMPLOYMENT_CATEGORY))
            .order_by(SupportResource.name)
            .all()
        )
        return [_orm_to_normalized(r) for r in rows]
    except SQLAlchemyError:
        logger.exception("Database query failed in jobs_service._load_jobs_from_db")
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def get_job_resources(db: Session) -> list[dict[str, Any]]:
    """Return all verified Employment resources, normalized to the common format.

    Flow:
      1. If JOBS_API_URL is configured, attempt a live fetch and normalize.
      2. On any transport/parse/validation failure, fall back to PostgreSQL.
      3. If JOBS_API_URL is not configured, go directly to PostgreSQL.
      4. Database results are always marked is_live=False.

    Never raises — failures are logged and an empty list (not a crash)
    is returned so the recommendation pipeline degrades gracefully.
    """
    if _client:
        try:
            return fetch_with_fallback(
                _client,
                path="",
                source="Jobs API",
                fallback_loader=lambda: _load_jobs_from_db(db),
                params={"category": "employment", "location": "Pune", "state": "Maharashtra"},
            )
        except Exception:
            logger.exception("Unexpected error in jobs live fetch; using DB fallback")

    return _load_jobs_from_db(db)


def get_women_job_resources(db: Session) -> list[dict[str, Any]]:
    """Return Employment resources particularly relevant to women job-seekers.

    Filters the full Employment list to entries whose name or description
    contains women-specific keywords.  Falls back to the full list if the
    filter produces no results (safe for sparse data).
    """
    all_jobs = get_job_resources(db)
    women_jobs = [
        r for r in all_jobs
        if any(
            kw in (r.get("name", "") + " " + r.get("description", "")).lower()
            for kw in WOMEN_JOB_KEYWORDS
        )
    ]
    return women_jobs if women_jobs else all_jobs


def get_all_employment_resources(db: Session) -> list[dict[str, Any]]:
    """Convenience alias for get_job_resources().

    Provides a single named entry point for routes that need all
    employment resources regardless of women-specificity.
    """
    return get_job_resources(db)


def describe_job_sources() -> dict[str, Any]:
    """Return metadata about the current job data sources.

    Used by GET /jobs/sources so operators can verify whether a live API
    is active or the system is running from verified PostgreSQL records.
    """
    return {
        "live_api_configured": bool(_JOBS_API_URL),
        "live_api_url": _JOBS_API_URL or None,
        "fallback": "PostgreSQL verified data",
        "categories_served": [EMPLOYMENT_CATEGORY],
        "verified_resources": [
            {
                "name": "Mahaswayam Employment and Skill Guidance Centre",
                "source": "mahaswayam.gov.in (Maharashtra Skill Development Dept)",
            },
            {
                "name": "Mukhyamantri Yuva Karya Prashikshan Yojana",
                "source": "pune.gov.in (Maharashtra Government scheme)",
            },
            {
                "name": "SARTHI Skill Development Programme for Women",
                "source": "sarthi.maharashtra.gov.in (Maharashtra Government)",
            },
            {
                "name": "DAY-NULM Self-Help Group (SHG) Programme",
                "source": "pmc.gov.in (Pune Municipal Corporation)",
            },
        ],
        "note": (
            "No public unauthenticated JSON API is available for NCS (ncs.gov.in) "
            "or Mahaswayam job listings as of September 2026 — both portals require "
            "employer/institutional login for vacancy data. "
            "Set JOBS_API_URL in .env when a suitable public endpoint becomes available. "
            "Current data is served from verified PostgreSQL records."
        ),
    }
