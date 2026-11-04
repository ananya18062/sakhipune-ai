"""category_router.py — Central intent-to-category routing for SakhiPune AI.

This module is the single place that maps every NLP intent to a category
service.  It is used by both:
  • POST /route  (the universal routed endpoint)
  • POST /recommend  (unchanged — still queries all resources)

The router does NOT replace the recommendation algorithm.  It only decides
which category service fetches the candidate resources.

Design: all loader lookups use getattr on this module at call time (not
function references stored at import time). This means unittest.mock.patch
works correctly on any loader function.

Intent → loader function in this module
─────────────────────────────────────────
  emergency          → get_all_emergency_resources
  legal              → get_all_legal_resources
  healthcare         → get_all_healthcare_resources
  counselling        → get_all_counselling_resources
  domestic_violence  → [get_all_legal + get_all_emergency + get_all_counselling]
  employment         → get_all_employment_resources
  education          → get_education_and_scholarship_resources
  government_scheme  → get_all_government_resources
  financial_support  → get_all_financial_resources
  shelter            → get_all_shelter_resources

Category override examples:
  category="internships"       → get_all_internship_resources
  category="safety"            → get_all_emergency_resources
  category="government_schemes"→ get_all_government_resources

Unknown intent → get_all_resources (full DB)

Public API
──────────
  route_query(intent, db, category, preferences)
      → (list[dict], safety_note | None)

  describe_route(intent, category)
      → dict
"""

from __future__ import annotations

import sys as _sys
import logging
from typing import Any

from sqlalchemy.orm import Session

# All loader functions are imported into this module's namespace so that
# patch("app.services.category_router.get_all_emergency_resources") works.

from app.services.emergency_service    import get_all_emergency_resources       # noqa: F401
from app.services.legal_service        import get_all_legal_resources           # noqa: F401
from app.services.healthcare_service   import get_all_healthcare_resources      # noqa: F401
from app.services.counselling_service  import get_all_counselling_resources     # noqa: F401
from app.services.jobs_service         import get_all_employment_resources      # noqa: F401
from app.services.internship_service   import get_all_internship_resources      # noqa: F401
from app.services.education_service    import get_education_and_scholarship_resources  # noqa: F401
from app.services.government_service   import get_all_government_resources      # noqa: F401
from app.services.financial_service    import get_all_financial_resources       # noqa: F401
from app.services.shelter_service      import get_all_shelter_resources         # noqa: F401
from app.services.resource_service     import get_all_resources                 # noqa: F401

logger = logging.getLogger(__name__)

# ── Dispatch tables (string keys only — no function references) ───────────────

_INTENT_FN: dict[str, str] = {
    "emergency":         "get_all_emergency_resources",
    "legal":             "get_all_legal_resources",
    "healthcare":        "get_all_healthcare_resources",
    "counselling":       "get_all_counselling_resources",
    "employment":        "get_all_employment_resources",
    "education":         "get_education_and_scholarship_resources",
    "government_scheme": "get_all_government_resources",
    "financial_support": "get_all_financial_resources",
    "shelter":           "get_all_shelter_resources",
}

_CATEGORY_FN: dict[str, str] = {
    "internships":          "get_all_internship_resources",
    "education":            "get_education_and_scholarship_resources",
    "jobs":                 "get_all_employment_resources",
    "legal":                "get_all_legal_resources",
    "healthcare":           "get_all_healthcare_resources",
    "counselling":          "get_all_counselling_resources",
    "safety":               "get_all_emergency_resources",
    "safety_and_emergency": "get_all_emergency_resources",
    "shelter":              "get_all_shelter_resources",
    "financial_support":    "get_all_financial_resources",
    "government_scheme":    "get_all_government_resources",
    "government_schemes":   "get_all_government_resources",
}

_DV_FNS: list[str] = [
    "get_all_legal_resources",
    "get_all_emergency_resources",
    "get_all_counselling_resources",
]

_EMERGENCY_SAFETY_NOTE = (
    "⚠ For immediate danger call 100 (Police) or 112 (National Emergency). "
    "SakhiPune AI provides resource information only — it does not directly assist emergencies."
)
_COUNSELLING_SAFETY_NOTE = (
    "For immediate mental health support call iCALL at 9152987821 (free, confidential). "
    "This system provides counselling resource information only."
)
_SHELTER_SAFETY_NOTE = (
    "Women in immediate danger should call 100 (Police) or 112 (Emergency) first. "
    "This system provides shelter resource information only."
)

_SAFETY_NOTES: dict[str, str] = {
    "get_all_emergency_resources":   _EMERGENCY_SAFETY_NOTE,
    "get_all_counselling_resources": _COUNSELLING_SAFETY_NOTE,
    "get_all_shelter_resources":     _SHELTER_SAFETY_NOTE,
}


# ── Core helpers ──────────────────────────────────────────────────────────────

def _get_fn(name: str):
    """Look up a loader by name in this module at call time.

    Using getattr at call time (not import time) means
    unittest.mock.patch can replace the binding and tests work correctly.
    """
    return getattr(_sys.modules[__name__], name)


def _resolve_fn_name(
    intent: str, category: str | None
) -> tuple[str | list[str], str | None]:
    """Return (fn_name_or_list, safety_note).

    Priority:
      1. Category override
      2. domestic_violence multi-service list
      3. Intent mapping
      4. General/unknown → full DB
    """
    cat_key = (category or "").strip().lower().replace("-", "_").replace(" ", "_")

    if cat_key and cat_key in _CATEGORY_FN:
        fn_name = _CATEGORY_FN[cat_key]
        return fn_name, _SAFETY_NOTES.get(fn_name)

    if intent == "domestic_violence":
        return _DV_FNS, (
            _EMERGENCY_SAFETY_NOTE + " Legal and counselling resources are also shown."
        )

    if intent in _INTENT_FN:
        fn_name = _INTENT_FN[intent]
        return fn_name, _SAFETY_NOTES.get(fn_name)

    return "get_all_resources", None


def _resolve_loader(intent: str, category: str | None) -> tuple[Any, str | None]:
    """Compatibility shim — returns actual function(s), not names."""
    fn_name, note = _resolve_fn_name(intent, category)
    if isinstance(fn_name, list):
        return [_get_fn(n) for n in fn_name], note
    return _get_fn(fn_name), note


# ── Public API ────────────────────────────────────────────────────────────────

def route_query(
    intent: str,
    db: Session,
    category: str | None = None,
    preferences: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch the correct resources for this intent/category pair.

    Returns:
        (resources, safety_note)
        resources    — normalized resource dicts ready for the pipeline
        safety_note  — string to surface to the user, or None

    Never raises.
    """
    fn_name, safety_note = _resolve_fn_name(intent, category)

    try:
        if isinstance(fn_name, list):
            seen: set[str] = set()
            merged: list[dict[str, Any]] = []
            for name in fn_name:
                for r in _get_fn(name)(db):
                    key = r.get("name", "")
                    if key not in seen:
                        seen.add(key)
                        merged.append(r)
            return merged, safety_note

        if fn_name in ("get_all_internship_resources", "get_all_employment_resources"):
            return _get_fn(fn_name)(db, preferences=preferences), safety_note

        return _get_fn(fn_name)(db), safety_note

    except Exception:
        logger.exception(
            "category_router: resource fetch failed for intent=%s category=%s", intent, category
        )
        return [], safety_note


def describe_route(intent: str, category: str | None = None) -> dict[str, Any]:
    """Return a human-readable description of which service handles this request."""
    fn_name, safety_note = _resolve_fn_name(intent, category)

    if isinstance(fn_name, list):
        # Map fn names → module names for display
        service_names = []
        for n in fn_name:
            fn = _get_fn(n)
            service_names.append(fn.__module__.split(".")[-1])
    else:
        service_names = [_get_fn(fn_name).__module__.split(".")[-1]]

    return {
        "intent":      intent,
        "category":    category,
        "services":    service_names,
        "safety_note": safety_note,
    }
