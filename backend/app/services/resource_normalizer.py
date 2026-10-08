"""resource_normalizer.py — Shared normalization utilities for SakhiPune AI.

This module is the single point of normalization logic for converting both:
  • External API payloads (live, source_type="api")
  • PostgreSQL SupportResource ORM rows (database, source_type="database")
into the common resource format consumed by the recommendation pipeline
and surfaced through the API response.

Common resource format (all fields always present)
───────────────────────────────────────────────────
  name          str   required — resource/organisation name
  category      str   required — resource category
  description   str   optional, defaults to ""
  location      str   optional, defaults to ""
  contact       str   optional — phone, email, or URL
  url           str   optional — https URL if available, else ""
  language      str   optional, defaults to "en"
  source        str   data origin label
  source_type   str   "api" | "official_data" | "database"
  last_updated  str   ISO date string or ""
  is_live       bool  True only when data came from a successful live API call

Compatibility with the recommendation pipeline
───────────────────────────────────────────────
  The recommendation pipeline (recommendation_service.py) expects ORM-like
  objects with attribute access.  Normalized dicts are converted back to
  lightweight synthetic ORM objects in routes.py via _dict_to_orm().

  The TF-IDF scorer (tfidf_service.build_resource_text) reads the "keywords"
  field from resources.  For ORM rows the real keywords column is used; for
  normalized dicts the keywords field is preserved in the dict so that
  _dict_to_orm() can forward it to the synthetic ORM object.

Public API
──────────
  orm_to_normalized(resource, *, source, source_type, is_live)
      Convert one SupportResource ORM row → normalized dict.

  normalize_from_dict(payload, *, source, source_type, is_live)
      Alias for normalize_resource() from base_client with consistent defaults.

  NORMALIZED_KEYS
      Tuple of the 11 canonical output keys.

  validate_normalized(d)
      Raise ValueError if required keys are missing or empty.
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.models import SupportResource
from app.services.api_clients.base_client import (
    ExternalAPIError,
    normalize_resource as _base_normalize,
)

logger = logging.getLogger(__name__)

# ── Canonical field list ──────────────────────────────────────────────────────

NORMALIZED_KEYS: tuple[str, ...] = (
    "name", "category", "description", "location", "contact",
    "url", "language", "source", "source_type", "last_updated", "is_live",
)

# "keywords" is an internal field carried alongside the normalized dict
# so that _dict_to_orm() in routes.py can forward it to the TF-IDF scorer.
# It is NOT part of the common format and is NOT included in NORMALIZED_KEYS.
_INTERNAL_KEYS = ("keywords",)


# ── ORM row → normalized dict ─────────────────────────────────────────────────

def orm_to_normalized(
    resource: SupportResource,
    *,
    source: str = "PostgreSQL verified data",
    source_type: str = "database",
    is_live: bool = False,
) -> dict[str, Any]:
    """Convert one SupportResource ORM row to the common normalized dict.

    Rules applied:
      • contact is promoted to url only when it begins with "https://"
        (phone numbers and short emergency codes are never treated as URLs)
      • language defaults to "en" when the DB column is NULL
      • last_updated is always "" for DB rows (no timestamp tracking yet)
      • keywords is included as an internal field so TF-IDF scoring remains
        accurate after the dict is converted back to a synthetic ORM object

    Returns a dict with all 11 canonical keys plus "keywords".
    Never raises — logs and falls back to empty strings on unexpected input.
    """
    try:
        contact = resource.contact or ""
        base = _base_normalize(
            {
                "name":         resource.name,
                "category":     resource.category,
                "description":  resource.description or "",
                "location":     resource.location or "",
                "contact":      contact,
                "url":          contact if contact.startswith("https://") else "",
                "language":     resource.language or "en",
                "last_updated": "",
            },
            source=source,
            source_type=source_type,
            is_live=is_live,
        ).as_dict()
    except (ExternalAPIError, ValueError):
        logger.exception(
            "resource_normalizer.orm_to_normalized: failed for resource id=%s name=%r",
            getattr(resource, "id", "?"),
            getattr(resource, "name", "?"),
        )
        return {}

    # Attach keywords as an internal field (not part of the canonical format)
    base["keywords"] = resource.keywords or ""
    return base


# ── API payload → normalized dict (thin wrapper for consistency) ──────────────

def normalize_from_dict(
    payload: dict[str, Any],
    *,
    source: str,
    source_type: str = "api",
    is_live: bool = True,
) -> dict[str, Any]:
    """Normalize one raw API payload dict to the common format.

    Thin wrapper around normalize_resource() from base_client that returns
    a plain dict (via .as_dict()) rather than a NormalizedResource dataclass.

    Raises ExternalAPIError on missing required fields or invalid source_type.
    """
    return _base_normalize(
        payload,
        source=source,
        source_type=source_type,
        is_live=is_live,
    ).as_dict()


# ── Validation ────────────────────────────────────────────────────────────────

def validate_normalized(d: dict[str, Any]) -> None:
    """Check that a normalized dict has all required canonical keys with values.

    Raises ValueError with a descriptive message on the first problem found.
    """
    if not isinstance(d, dict):
        raise ValueError(f"Expected a dict, got {type(d).__name__}")

    for key in NORMALIZED_KEYS:
        if key not in d:
            raise ValueError(f"Normalized resource is missing required key '{key}'")

    if not d.get("name", "").strip():
        raise ValueError("Normalized resource has an empty 'name' field")
    if not d.get("category", "").strip():
        raise ValueError("Normalized resource has an empty 'category' field")

    valid_types = {"api", "official_data", "database"}
    if d.get("source_type") not in valid_types:
        raise ValueError(
            f"source_type must be one of {valid_types}, got {d.get('source_type')!r}"
        )
