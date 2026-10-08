"""test_category_router.py — Tests for the central category router.

Patch targets are in the category_router namespace (where the functions are
imported), not in the originating service modules.

Coverage:
  Every intent → correct service mapping (9 tests)
  Category overrides intent (3 tests)
  domestic_violence → merged multi-service resources (2 tests)
  Unknown intent → full-DB fallback (1 test)
  Safety notes present for emergency/shelter/counselling (3 tests)
  Safety notes absent for non-safety intents (2 tests)
  route_query: never raises on service failure (1 test)
  route_query: internship preferences passed through (1 test)
  describe_route: returns correct service name (2 tests)
  /route endpoint: routes employment query (1 test)
  /route endpoint: safety note injected for emergency (1 test)
  /route/explain endpoint: returns service name (1 test)
  /route endpoint: 500 on NLP failure (1 test)
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CR = "app.services.category_router"   # patch target namespace


def _normalized(name="Test Resource", category="Employment"):
    return {
        "name": name, "category": category, "description": "Test",
        "location": "Pune", "contact": "1800-000-000", "url": "",
        "language": "en", "source": "PostgreSQL verified data",
        "source_type": "database", "last_updated": "", "is_live": False,
    }


def _make_db():
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value = q
    q.order_by.return_value = q
    q.all.return_value = []
    return db


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — Intent → loader mapping (tests 1–9)
# ─────────────────────────────────────────────────────────────────────────────

INTENT_LOADER_MAP = [
    ("emergency",         "get_all_emergency_resources"),
    ("legal",             "get_all_legal_resources"),
    ("healthcare",        "get_all_healthcare_resources"),
    ("counselling",       "get_all_counselling_resources"),
    ("employment",        "get_all_employment_resources"),
    ("education",         "get_education_and_scholarship_resources"),
    ("government_scheme", "get_all_government_resources"),
    ("financial_support", "get_all_financial_resources"),
    ("shelter",           "get_all_shelter_resources"),
]


@pytest.mark.parametrize("intent,fn_name", INTENT_LOADER_MAP)
def test_intent_routes_to_correct_loader(intent, fn_name):
    """Each NLP intent maps to the expected loader function."""
    from app.services import category_router as cr
    db = _make_db()
    with patch(f"{CR}.{fn_name}", return_value=[_normalized()]) as mock_fn:
        resources, _ = cr.route_query(intent, db)
    mock_fn.assert_called_once()
    assert len(resources) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Category overrides intent (tests 10–12)
# ─────────────────────────────────────────────────────────────────────────────

def test_internships_category_overrides_employment_intent():
    from app.services import category_router as cr
    db = _make_db()
    with patch(f"{CR}.get_all_internship_resources",
               return_value=[_normalized(category="Internships")]) as mock_fn:
        resources, _ = cr.route_query("employment", db, category="internships")
    mock_fn.assert_called_once()
    assert resources[0]["category"] == "Internships"


def test_safety_category_overrides_general_intent():
    from app.services import category_router as cr
    db = _make_db()
    with patch(f"{CR}.get_all_emergency_resources",
               return_value=[_normalized(category="Emergency")]) as mock_fn:
        resources, _ = cr.route_query("general", db, category="safety")
    mock_fn.assert_called_once()


def test_government_schemes_category_overrides_unknown_intent():
    from app.services import category_router as cr
    db = _make_db()
    with patch(f"{CR}.get_all_government_resources",
               return_value=[_normalized(category="Government Schemes")]) as mock_fn:
        resources, _ = cr.route_query("general", db, category="government_schemes")
    mock_fn.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Unknown intent → full DB fallback (test 13)
# ─────────────────────────────────────────────────────────────────────────────

def test_unknown_intent_uses_full_db_fallback():
    from app.services import category_router as cr
    db = _make_db()
    with patch(f"{CR}.get_all_resources", return_value=[_normalized()]) as mock_fn:
        resources, note = cr.route_query("xyzunknown", db)
    mock_fn.assert_called_once()
    assert note is None
    assert len(resources) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — domestic_violence merges three services (tests 14–15)
# ─────────────────────────────────────────────────────────────────────────────

def test_dv_merges_legal_emergency_counselling():
    from app.services import category_router as cr
    db = _make_db()
    with (
        patch(f"{CR}.get_all_legal_resources",
              return_value=[_normalized("Legal Aid", "Legal Support")]),
        patch(f"{CR}.get_all_emergency_resources",
              return_value=[_normalized("Emergency Help", "Emergency")]),
        patch(f"{CR}.get_all_counselling_resources",
              return_value=[_normalized("Counselling", "Counselling")]),
    ):
        resources, note = cr.route_query("domestic_violence", db)

    assert len(resources) == 3
    cats = {r["category"] for r in resources}
    assert cats == {"Legal Support", "Emergency", "Counselling"}
    assert note is not None


def test_dv_deduplicates_shared_resources():
    from app.services import category_router as cr
    db = _make_db()
    shared = _normalized("Shared Centre", "Emergency")
    with (
        patch(f"{CR}.get_all_legal_resources",   return_value=[shared]),
        patch(f"{CR}.get_all_emergency_resources", return_value=[shared]),
        patch(f"{CR}.get_all_counselling_resources", return_value=[]),
    ):
        resources, _ = cr.route_query("domestic_violence", db)
    assert len(resources) == 1   # deduplicated by name


# ─────────────────────────────────────────────────────────────────────────────
# Section 5 — Safety notes (tests 16–20)
# ─────────────────────────────────────────────────────────────────────────────

def test_emergency_intent_has_safety_note():
    from app.services.category_router import _resolve_loader
    _, note = _resolve_loader("emergency", None)
    assert note is not None
    assert any(kw in note for kw in ["100", "112", "danger", "emergency"])


def test_shelter_intent_has_safety_note():
    from app.services.category_router import _resolve_loader
    _, note = _resolve_loader("shelter", None)
    assert note is not None


def test_counselling_intent_has_safety_note():
    from app.services.category_router import _resolve_loader
    _, note = _resolve_loader("counselling", None)
    assert note is not None


def test_employment_intent_has_no_safety_note():
    from app.services.category_router import _resolve_loader
    _, note = _resolve_loader("employment", None)
    assert note is None


def test_education_intent_has_no_safety_note():
    from app.services.category_router import _resolve_loader
    _, note = _resolve_loader("education", None)
    assert note is None


# ─────────────────────────────────────────────────────────────────────────────
# Section 6 — Robustness (tests 21–22)
# ─────────────────────────────────────────────────────────────────────────────

def test_route_query_never_raises_on_service_error():
    from app.services import category_router as cr
    db = _make_db()
    with patch(f"{CR}.get_all_emergency_resources", side_effect=RuntimeError("boom")):
        resources, note = cr.route_query("emergency", db)
    assert resources == []   # graceful empty list, no crash


def test_internship_preferences_passed_through():
    from app.services import category_router as cr
    db = _make_db()
    prefs = {"interest_area": "Technology", "work_type": "On-site"}
    captured = {}

    def fake_internships(db, preferences=None):
        captured["preferences"] = preferences
        return []

    with patch(f"{CR}.get_all_internship_resources", side_effect=fake_internships):
        cr.route_query("employment", db, category="internships", preferences=prefs)

    assert captured.get("preferences") == prefs


# ─────────────────────────────────────────────────────────────────────────────
# Section 7 — describe_route (tests 23–24)
# ─────────────────────────────────────────────────────────────────────────────

def test_describe_legal_intent():
    from app.services.category_router import describe_route
    info = describe_route("legal")
    assert "legal_service" in info["services"]
    assert info["intent"] == "legal"


def test_describe_internships_category_override():
    from app.services.category_router import describe_route
    info = describe_route("employment", category="internships")
    assert "internship_service" in info["services"]


# ─────────────────────────────────────────────────────────────────────────────
# Section 8 — /route and /route/explain route tests (tests 25–28)
# ─────────────────────────────────────────────────────────────────────────────

ROUTES = "app.api.routes"   # patch target for route endpoint tests

def test_route_endpoint_employment_query():
    from app.api import routes
    from app.models.schemas import SupportRequest

    normalized = _normalized("Mahaswayam Centre", "Employment")
    db = MagicMock()

    with patch(f"{ROUTES}.route_query", return_value=([normalized], None)):
        response = routes.route_recommend(
            SupportRequest(message="I need a job in Pune", language="en"), db
        )

    assert response.intent == "employment"
    assert len(response.recommendations) >= 1


def test_route_endpoint_emergency_safety_note_injected():
    from app.api import routes
    from app.models.schemas import SupportRequest

    normalized = _normalized("Police Helpline", "Emergency")
    safety_note = "⚠ For immediate danger call 100."
    db = MagicMock()

    with patch(f"{ROUTES}.route_query", return_value=([normalized], safety_note)):
        response = routes.route_recommend(
            SupportRequest(message="I am in danger", language="en"), db
        )

    assert response.recommendations
    assert "100" in (response.recommendations[0].reason or "")


def test_route_explain_endpoint():
    from app.api import routes
    result = routes.route_explain("legal")
    assert "legal_service" in result["services"]


def test_route_endpoint_nlp_failure_returns_500(monkeypatch):
    from app.api import routes
    from app.models.schemas import SupportRequest
    import json

    monkeypatch.setattr(routes, "classify_intent",
                        lambda _msg: (_ for _ in ()).throw(RuntimeError("nlp down")))
    resp = routes.route_recommend(SupportRequest(message="I need help"), object())
    assert resp.status_code == 500
    body = json.loads(resp.body.decode())
    assert body["error"] == "NLP_ERROR"
