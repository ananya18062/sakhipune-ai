"""test_hybrid_fallback.py — Comprehensive hybrid API + PostgreSQL fallback tests.

Verifies that every category service correctly implements the flow:
  External API (when configured) → normalize → recommendation
  On any failure                 → PostgreSQL → normalize → recommendation

All transport is mocked — no live network or database calls.

Failure modes tested per service (5 each):
  1. API timeout           → DB fallback, is_live=False
  2. Connection error      → DB fallback, is_live=False
  3. HTTP 4xx              → DB fallback, is_live=False
  4. HTTP 5xx              → DB fallback, is_live=False
  5. Malformed JSON        → DB fallback, is_live=False

Plus for each service:
  6. Success path          → is_live=True (when API URL is configured)
  7. Empty API response    → empty list, no crash
  8. DB fallback marks source_type=database, is_live=False

api_availability module tests:
  9.  get_availability() returns all 10 categories
  10. No category has status="available" (none verified yet)
  11. is_api_available() returns False for all categories
  12. GET /api/availability endpoint returns correct shape
"""

from __future__ import annotations

import io
import os
import sys
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body


def _make_http_error(code: int) -> HTTPError:
    return HTTPError("https://fake.example/", code, f"HTTP {code}", {}, io.BytesIO())


def _make_orm(name="Resource", category="Employment"):
    r = MagicMock()
    r.id = 1
    r.name = name
    r.category = category
    r.description = "Test description"
    r.location = "Pune"
    r.contact = "https://example.gov.in"
    r.language = "en"
    r.keywords = ""
    return r


def _make_db(*resources):
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value = q
    q.order_by.return_value = q
    q.all.return_value = list(resources)
    return db


def _make_client_with(opener):
    from app.services.api_clients.base_client import BaseAPIClient
    return BaseAPIClient("https://fake.example/", opener=opener)


# ─────────────────────────────────────────────────────────────────────────────
# Parametrized service config
# ─────────────────────────────────────────────────────────────────────────────

SERVICE_CONFIG = [
    ("education_service",   "get_education_resources",    "_client", "Education"),
    ("jobs_service",        "get_job_resources",          "_client", "Employment"),
    ("internship_service",  "get_internship_resources",   "_client", "Internships"),
    ("healthcare_service",  "get_healthcare_resources",   "_client", "Healthcare"),
    ("legal_service",       "get_legal_resources",        "_client", "Legal Support"),
    ("financial_service",   "get_financial_resources",    "_client", "Financial Support"),
    ("shelter_service",     "get_shelter_resources",      "_client", "Shelters"),
    ("emergency_service",   "get_emergency_resources",    "_client", "Emergency"),
    ("counselling_service", "get_counselling_resources",  "_client", "Counselling"),
    ("government_service",  "get_government_resources",   "_client", "Government Schemes"),
]

SERVICE_IDS = [cfg[0] for cfg in SERVICE_CONFIG]


def _call_service(module_name, fn_name, db, **kwargs):
    import importlib
    mod = importlib.import_module(f"app.services.{module_name}")
    fn  = getattr(mod, fn_name)
    return fn(db, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — API timeout → DB fallback (10 tests, one per service)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module_name,fn_name,client_attr,category", SERVICE_CONFIG, ids=SERVICE_IDS)
def test_timeout_falls_back_to_db(module_name, fn_name, client_attr, category):
    import importlib
    mod = importlib.import_module(f"app.services.{module_name}")
    db  = _make_db(_make_orm(category=category))
    fake = _make_client_with(lambda req, timeout: (_ for _ in ()).throw(TimeoutError()))

    with patch.object(mod, client_attr, fake):
        result = _call_service(module_name, fn_name, db)

    assert len(result) == 1
    assert result[0]["is_live"] is False
    assert result[0]["source_type"] == "database"


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Connection error → DB fallback
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module_name,fn_name,client_attr,category", SERVICE_CONFIG, ids=SERVICE_IDS)
def test_connection_error_falls_back_to_db(module_name, fn_name, client_attr, category):
    import importlib
    mod = importlib.import_module(f"app.services.{module_name}")
    db  = _make_db(_make_orm(category=category))
    fake = _make_client_with(lambda req, timeout: (_ for _ in ()).throw(URLError("unreachable")))

    with patch.object(mod, client_attr, fake):
        result = _call_service(module_name, fn_name, db)

    assert result[0]["is_live"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — HTTP 4xx → DB fallback
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module_name,fn_name,client_attr,category", SERVICE_CONFIG, ids=SERVICE_IDS)
def test_http_4xx_falls_back_to_db(module_name, fn_name, client_attr, category):
    import importlib
    mod = importlib.import_module(f"app.services.{module_name}")
    db  = _make_db(_make_orm(category=category))
    fake = _make_client_with(
        lambda req, timeout: (_ for _ in ()).throw(_make_http_error(403))
    )

    with patch.object(mod, client_attr, fake):
        result = _call_service(module_name, fn_name, db)

    assert result[0]["is_live"] is False
    assert result[0]["source"] == "PostgreSQL verified data"


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — HTTP 5xx → DB fallback
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module_name,fn_name,client_attr,category", SERVICE_CONFIG, ids=SERVICE_IDS)
def test_http_5xx_falls_back_to_db(module_name, fn_name, client_attr, category):
    import importlib
    mod = importlib.import_module(f"app.services.{module_name}")
    db  = _make_db(_make_orm(category=category))
    fake = _make_client_with(
        lambda req, timeout: (_ for _ in ()).throw(_make_http_error(503))
    )

    with patch.object(mod, client_attr, fake):
        result = _call_service(module_name, fn_name, db)

    assert result[0]["is_live"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Section 5 — Malformed JSON → DB fallback
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module_name,fn_name,client_attr,category", SERVICE_CONFIG, ids=SERVICE_IDS)
def test_malformed_json_falls_back_to_db(module_name, fn_name, client_attr, category):
    import importlib
    mod = importlib.import_module(f"app.services.{module_name}")
    db  = _make_db(_make_orm(category=category))
    fake = _make_client_with(lambda req, timeout: FakeResponse(b"not-json{{{"))

    with patch.object(mod, client_attr, fake):
        result = _call_service(module_name, fn_name, db)

    assert result[0]["is_live"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Section 6 — Success path: live API response → is_live=True
# ─────────────────────────────────────────────────────────────────────────────

def _live_payload(category: str) -> bytes:
    import json
    return json.dumps({"data": [
        {"name": "Live Resource", "category": category, "description": "From live API"}
    ]}).encode()


@pytest.mark.parametrize("module_name,fn_name,client_attr,category", SERVICE_CONFIG, ids=SERVICE_IDS)
def test_success_path_marks_is_live_true(module_name, fn_name, client_attr, category):
    import importlib
    mod = importlib.import_module(f"app.services.{module_name}")
    db  = _make_db()
    fake = _make_client_with(lambda req, timeout: FakeResponse(_live_payload(category)))

    with patch.object(mod, client_attr, fake):
        result = _call_service(module_name, fn_name, db)

    assert len(result) == 1
    assert result[0]["is_live"] is True
    assert result[0]["name"] == "Live Resource"


# ─────────────────────────────────────────────────────────────────────────────
# Section 7 — Empty API response → empty list, no crash
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module_name,fn_name,client_attr,category", SERVICE_CONFIG, ids=SERVICE_IDS)
def test_empty_api_response_returns_empty_list(module_name, fn_name, client_attr, category):
    import importlib
    mod = importlib.import_module(f"app.services.{module_name}")
    db  = _make_db()  # empty DB too
    fake = _make_client_with(lambda req, timeout: FakeResponse(b'{"data": []}'))

    with patch.object(mod, client_attr, fake):
        result = _call_service(module_name, fn_name, db)

    assert result == []   # no crash, empty list


# ─────────────────────────────────────────────────────────────────────────────
# Section 8 — No API configured → DB fallback active (current default)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module_name,fn_name,client_attr,category", SERVICE_CONFIG, ids=SERVICE_IDS)
def test_no_api_configured_uses_db(module_name, fn_name, client_attr, category):
    """When *_API_URL is empty (default), service goes straight to DB."""
    import importlib
    mod = importlib.import_module(f"app.services.{module_name}")
    db  = _make_db(_make_orm(category=category))

    # Ensure _client is None (simulates no API URL configured)
    with patch.object(mod, client_attr, None):
        result = _call_service(module_name, fn_name, db)

    assert len(result) == 1
    assert result[0]["is_live"] is False
    assert result[0]["source_type"] == "database"


# ─────────────────────────────────────────────────────────────────────────────
# Section 9 — api_availability module
# ─────────────────────────────────────────────────────────────────────────────

class TestApiAvailability:

    def test_get_availability_returns_all_categories(self):
        from app.services.api_availability import get_availability, AVAILABILITY
        result = get_availability()
        assert "categories" in result
        assert len(result["categories"]) == len(AVAILABILITY)
        for cat in ["education", "employment", "internships", "healthcare", "legal",
                    "financial_support", "shelter", "emergency", "counselling",
                    "government_scheme"]:
            assert cat in result["categories"]

    def test_no_category_has_status_available(self):
        """No API is verified as publicly available — all should be non-available."""
        from app.services.api_availability import AVAILABILITY
        available = [k for k, v in AVAILABILITY.items() if v["status"] == "available"]
        assert available == [], f"Unexpected available APIs: {available}"

    def test_is_api_available_returns_false_for_all(self):
        from app.services.api_availability import is_api_available, AVAILABILITY
        for category in AVAILABILITY:
            assert is_api_available(category) is False

    def test_get_availability_has_summary(self):
        from app.services.api_availability import get_availability
        result = get_availability()
        assert "summary" in result
        assert result["summary"]["total"] == 10
        assert result["summary"]["available"] == 0
        assert "fallback_active" in result["summary"]

    def test_every_category_has_fallback_field(self):
        from app.services.api_availability import AVAILABILITY
        for cat, info in AVAILABILITY.items():
            assert "fallback" in info, f"Missing fallback for {cat}"
            assert "PostgreSQL" in info["fallback"]

    def test_every_category_has_last_verified(self):
        from app.services.api_availability import AVAILABILITY
        for cat, info in AVAILABILITY.items():
            assert "last_verified" in info, f"Missing last_verified for {cat}"
            assert info["last_verified"], f"Empty last_verified for {cat}"

    def test_api_availability_endpoint(self):
        from app.api.routes import api_availability
        result = api_availability()
        assert "categories" in result
        assert "summary" in result
        assert "note" in result
        assert result["summary"]["available"] == 0
