"""filter_utils.py — Shared structured filter helpers for SakhiPune AI.

All service-layer filter functions live here so the filter logic is
defined once and tested in one place.

Filter design principles
────────────────────────
  • AND logic: every active filter must match for a resource to be included.
  • Unknown = excluded: if a resource has work_mode=NULL and the user asked
    for "remote", that resource is excluded (not assumed to be remote).
  • Default = include: if a filter value is None or a catch-all token
    ("any", "all work modes", "all", ""), the filter is inactive.
  • Soft-fall-through: each filter falls back to the unfiltered set only
    if the FINAL combined result is empty (not per-filter). This prevents
    a single unsatisfiable filter from silently returning unrelated results.

Public API
──────────
  apply_job_filters(resources, *, experience_filter, work_mode_filter, employment_type_filter)
      → list[dict]

  apply_internship_filters(resources, *, experience_filter, work_mode_filter)
      → list[dict]

  apply_education_filters(resources, *, delivery_mode_filter)
      → list[dict]

  filter_active(value)
      → bool  (True when the filter value should restrict results)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Sentinel values that mean "no filter" ────────────────────────────────────

_EXPERIENCE_NO_FILTER = {None, "", "any_experience", "any experience", "any"}
_WORK_MODE_NO_FILTER   = {None, "", "all_work_modes", "all work modes", "all"}
_DELIVERY_NO_FILTER    = {None, "", "all", "all_modes", "all modes"}

# Frontend option → DB value mapping
# These must match the values stored in the experience_level / work_mode columns.

EXPERIENCE_MAP: dict[str, str] = {
    "any_experience":      "any",
    "any experience":      "any",
    "any":                 "any",
    "fresher":             "fresher",
    "fresher_no_experience": "fresher",
    "fresher / no experience": "fresher",
    "no experience":       "fresher",
    "less_than_1":         "less_than_1",
    "less than 1 year":    "less_than_1",
    "less than 1":         "less_than_1",
    "1_2_years":           "1_2_years",
    "1-2 years":           "1_2_years",
    "1–2 years":           "1_2_years",
    "3_5_years":           "3_5_years",
    "3-5 years":           "3_5_years",
    "3–5 years":           "3_5_years",
    "6_10_years":          "6_10_years",
    "6-10 years":          "6_10_years",
    "6–10 years":          "6_10_years",
    "more_than_10":        "more_than_10",
    "more than 10 years":  "more_than_10",
    "10+ years":           "more_than_10",
}

WORK_MODE_MAP: dict[str, str] = {
    "remote":              "remote",
    "remote / work from home": "remote",
    "work from home":      "remote",
    "wfh":                 "remote",
    "hybrid":              "hybrid",
    "on_site":             "on_site",
    "on-site":             "on_site",
    "onsite":              "on_site",
    "in office":           "on_site",
    "in-office":           "on_site",
}

EMPLOYMENT_TYPE_MAP: dict[str, str] = {
    "full_time":           "full_time",
    "full time":           "full_time",
    "part_time":           "part_time",
    "part time":           "part_time",
    "contract":            "contract",
    "apprenticeship":      "apprenticeship",
    "internship":          "apprenticeship",
    "self_employment":     "self_employment",
    "self employment":     "self_employment",
    "freelance":           "self_employment",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def filter_active(value: str | None) -> bool:
    """Return True when a filter value should actually restrict results."""
    return bool(value and value.strip())


def _normalise(value: str | None) -> str:
    return (value or "").strip().lower()


def _resolve_experience(raw: str | None) -> str | None:
    """Map a frontend experience string to the DB vocabulary token, or None."""
    if not raw:
        return None
    normalised = _normalise(raw)
    if normalised in _EXPERIENCE_NO_FILTER:
        return None
    return EXPERIENCE_MAP.get(normalised) or normalised


def _resolve_work_mode(raw: str | None) -> str | None:
    """Map a frontend work-mode string to the DB vocabulary token, or None."""
    if not raw:
        return None
    normalised = _normalise(raw)
    if normalised in _WORK_MODE_NO_FILTER:
        return None
    return WORK_MODE_MAP.get(normalised) or normalised


def _resolve_employment_type(raw: str | None) -> str | None:
    """Map a frontend employment-type string to the DB vocabulary token, or None."""
    if not raw:
        return None
    normalised = _normalise(raw)
    return EMPLOYMENT_TYPE_MAP.get(normalised) or (normalised if normalised else None)


def _experience_matches(resource: dict[str, Any], wanted: str | None) -> bool:
    """Return True if the resource's experience level satisfies the filter.

    Matching rules:
      • wanted = None         → no filter, always matches
      • resource level = "any" → accepts all levels, always matches
      • wanted = "fresher"   → resource must be "fresher" or "any"
      • otherwise            → resource level must exactly equal wanted
      • resource level = None (unknown) → does NOT match (excluded from results)
    """
    if wanted is None:
        return True
    resource_level = (resource.get("experience_level") or "").strip().lower()
    if not resource_level:
        # Unknown experience — cannot confirm it satisfies the filter
        return False
    if resource_level == "any":
        return True
    return resource_level == wanted


def _work_mode_matches(resource: dict[str, Any], wanted: str | None) -> bool:
    """Return True if the resource's work mode satisfies the filter.

    Unknown work mode (NULL) never matches a specific work-mode filter.
    """
    if wanted is None:
        return True
    resource_mode = (resource.get("work_mode") or "").strip().lower()
    if not resource_mode:
        return False
    return resource_mode == wanted


def _employment_type_matches(resource: dict[str, Any], wanted: str | None) -> bool:
    """Return True if the resource's employment type satisfies the filter."""
    if wanted is None:
        return True
    resource_type = (resource.get("employment_type") or "").strip().lower()
    if not resource_type:
        return False
    return resource_type == wanted


# ── Public filter functions ───────────────────────────────────────────────────

def apply_job_filters(
    resources: list[dict[str, Any]],
    *,
    experience_filter: str | None = None,
    work_mode_filter: str | None = None,
    employment_type_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Apply AND-combined structured filters to a list of job resource dicts.

    Each active filter must be satisfied for a resource to be included.
    If the combined result is empty AND at least one filter was active,
    return the original list so the UI always has something to show —
    BUT log a warning so the operator knows no resources matched.

    IMPORTANT: If work_mode_filter = "remote" and a resource has
    work_mode = NULL (unknown), that resource is excluded.  We never
    assume a resource is remote just because we don't know its work mode.
    """
    wanted_exp  = _resolve_experience(experience_filter)
    wanted_mode = _resolve_work_mode(work_mode_filter)
    wanted_type = _resolve_employment_type(employment_type_filter)

    any_active = any(v is not None for v in (wanted_exp, wanted_mode, wanted_type))
    if not any_active:
        return resources  # no filters selected — show everything

    filtered = [
        r for r in resources
        if (
            _experience_matches(r, wanted_exp)
            and _work_mode_matches(r, wanted_mode)
            and _employment_type_matches(r, wanted_type)
        )
    ]

    if not filtered:
        logger.warning(
            "apply_job_filters: no resources matched "
            "experience=%r work_mode=%r employment_type=%r — returning empty set",
            wanted_exp, wanted_mode, wanted_type,
        )
        # Return empty list — the API layer will show the "no results" message.
        # Do NOT silently substitute unrelated resources.
        return []

    return filtered


def apply_internship_filters(
    resources: list[dict[str, Any]],
    *,
    experience_filter: str | None = None,
    work_mode_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Apply structured filters to internship resources (subset of job filters)."""
    wanted_exp  = _resolve_experience(experience_filter)
    wanted_mode = _resolve_work_mode(work_mode_filter)

    any_active = any(v is not None for v in (wanted_exp, wanted_mode))
    if not any_active:
        return resources

    filtered = [
        r for r in resources
        if (
            _experience_matches(r, wanted_exp)
            and _work_mode_matches(r, wanted_mode)
        )
    ]

    if not filtered:
        logger.warning(
            "apply_internship_filters: no internships matched "
            "experience=%r work_mode=%r", wanted_exp, wanted_mode,
        )
        return []

    return filtered


def apply_education_filters(
    resources: list[dict[str, Any]],
    *,
    delivery_mode_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Apply delivery-mode filter to education resources.

    Education resources do not have a structured delivery_mode column yet.
    This function uses keyword matching in description/name as a proxy
    until the column is added in a future migration.
    """
    if not delivery_mode_filter:
        return resources
    normalised = _normalise(delivery_mode_filter)
    if normalised in _DELIVERY_NO_FILTER:
        return resources

    ONLINE_KEYWORDS  = {"online", "virtual", "digital", "portal", "website", "e-learning"}
    OFFLINE_KEYWORDS = {"in-person", "in person", "campus", "centre", "college", "school", "classroom"}

    def _matches(r: dict[str, Any]) -> bool:
        text = " ".join([
            r.get("name", ""), r.get("description", ""), r.get("location", ""),
        ]).lower()
        if normalised == "online":
            return any(kw in text for kw in ONLINE_KEYWORDS)
        if normalised == "offline":
            return any(kw in text for kw in OFFLINE_KEYWORDS)
        return True  # hybrid — show everything

    filtered = [r for r in resources if _matches(r)]
    return filtered if filtered else resources
