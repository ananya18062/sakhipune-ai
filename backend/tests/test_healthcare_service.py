"""test_healthcare_service.py — Tests for healthcare_service.py and /healthcare endpoints.

All external I/O is mocked.  No live network or live database required.

Coverage:
  1.  NLP: "I need healthcare support"         → healthcare intent
  2.  NLP: "I need a hospital in Pune"         → healthcare intent
  3.  NLP: "I need healthcare help for women"  → healthcare intent
  4.  NLP: "I need maternal healthcare"        → healthcare intent
  5.  NLP: "I need gynaecology support"        → healthcare intent  (was MISS before patch)
  6.  NLP: "I want antenatal care"             → healthcare intent  (was MISS before patch)
  7.  Service: no resources → empty list, no crash
  8.  Service: API timeout → DB fallback, is_live=False
  9.  Service: API connection error → DB fallback
  10. Service: malformed API response → DB fallback
  11. Service: DB fallback marks source_type=database, is_live=False
  12. Service: get_maternal_healthcare_resources filters correctly
  13. Service: get_women_healthcare_resources filters correctly
  14. Service: describe_healthcare_sources returns expected shape
  15. Normalization: https contact promoted to url
  16. Normalization: phone contact NOT promoted to url
  17. /healthcare/sources endpoint returns correct shape
  18. /healthcare: 200 + recommendations for location-specific query
  19. /healthcare: 503 on DB failure
  20. /healthcare: 500 on pipeline failure
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.nlp_service import classify_intent


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_orm(
    name="Sassoon General Hospital (B.J. Medical College)",
    category="Healthcare",
    description="Largest government hospital in Pune with free OPD and emergency services for women.",
    location="Jai Prakash Narayan Road – Agarkar Nagar Pune 411001",
    contact="020-26128000",
    language="en",
    keywords="hospital,healthcare,government,women",
):
    r = MagicMock()
    r.id = 1
    r.name = name
    r.category = category
    r.description = description
    r.location = location
    r.contact = contact
    r.language = language
    r.keywords = keywords
    return r


def _make_orm_url(
    name="Pune Municipal Corporation – Health Centres",
    contact="https://pmc.gov.in",
    description="PMC primary health centres across Pune.",
    location="Pune Municipal Corporation – Shivajinagar Pune",
):
    return _make_orm(name=name, contact=contact, description=description, location=location)


def _make_db(*resources):
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value = q
    q.order_by.return_value = q
    q.all.return_value = list(resources)
    return db


def _svc():
    from app.services import healthcare_service
    return healthcare_service


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — NLP intent (tests 1–6)
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthcareNLP:
    def test_healthcare_support_is_healthcare(self):
        assert classify_intent("I need healthcare support")["intent"] == "healthcare"

    def test_hospital_in_pune_is_healthcare(self):
        assert classify_intent("I need a hospital in Pune")["intent"] == "healthcare"

    def test_women_healthcare_is_healthcare(self):
        assert classify_intent("I need healthcare help for women")["intent"] == "healthcare"

    def test_maternal_healthcare_is_healthcare(self):
        assert classify_intent("I need maternal healthcare")["intent"] == "healthcare"

    def test_gynaecology_support_is_healthcare(self):
        # Was MISS before NLP patch — now requires gynaecology keyword
        assert classify_intent("I need gynaecology support")["intent"] == "healthcare"

    def test_antenatal_care_is_healthcare(self):
        # Was MISS before NLP patch — now requires antenatal keyword
        assert classify_intent("I want antenatal care")["intent"] == "healthcare"


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Service unit tests (tests 7–16)
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthcareService:

    # 7. No resources → empty list, no crash
    def test_no_resources_returns_empty_list(self):
        svc = _svc()
        assert svc.get_healthcare_resources(_make_db()) == []

    # 8. API timeout → DB fallback, is_live=False
    def test_api_timeout_falls_back_to_db(self):
        svc = _svc()
        db = _make_db(_make_orm())

        def raise_timeout(req, timeout):
            raise TimeoutError()

        from app.services.api_clients.base_client import BaseAPIClient
        fake_client = BaseAPIClient("https://fake.example/", opener=raise_timeout)

        with patch.object(svc, "_client", fake_client):
            result = svc.get_healthcare_resources(db)

        assert len(result) == 1
        assert result[0]["is_live"] is False
        assert result[0]["source_type"] == "database"

    # 9. API URLError → DB fallback
    def test_api_connection_failure_falls_back_to_db(self):
        svc = _svc()
        db = _make_db(_make_orm())

        def raise_url_error(req, timeout):
            raise URLError("unreachable")

        from app.services.api_clients.base_client import BaseAPIClient
        fake_client = BaseAPIClient("https://fake.example/", opener=raise_url_error)

        with patch.object(svc, "_client", fake_client):
            result = svc.get_healthcare_resources(db)

        assert result[0]["is_live"] is False

    # 10. Malformed API response → DB fallback
    def test_malformed_api_response_falls_back_to_db(self):
        svc = _svc()
        db = _make_db(_make_orm())

        def bad_json(req, timeout):
            class R:
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def read(self): return b"not-json{"
            return R()

        from app.services.api_clients.base_client import BaseAPIClient
        fake_client = BaseAPIClient("https://fake.example/", opener=bad_json)

        with patch.object(svc, "_client", fake_client):
            result = svc.get_healthcare_resources(db)

        assert result[0]["is_live"] is False

    # 11. DB fallback marks records correctly
    def test_db_fallback_marks_not_live(self):
        svc = _svc()
        result = svc.get_healthcare_resources(_make_db(_make_orm()))
        assert result[0]["is_live"] is False
        assert result[0]["source_type"] == "database"
        assert result[0]["source"] == "PostgreSQL verified data"

    # 12. get_maternal_healthcare_resources filters to maternal resources
    def test_maternal_filter_returns_maternal_resources(self):
        svc = _svc()
        maternal = _make_orm(
            name="JSY – Janani Suraksha Yojana",
            description="Cash assistance for pregnant women delivering at government hospitals.",
        )
        general = _make_orm(name="General Clinic", description="General outpatient services.")
        db = _make_db(maternal, general)
        result = svc.get_maternal_healthcare_resources(db)
        names = [r["name"] for r in result]
        assert any("janani" in n.lower() or "jsy" in n.lower() for n in names)

    # 12b. Maternal filter falls back when no maternal resource exists
    def test_maternal_filter_falls_back_to_all(self):
        svc = _svc()
        general = _make_orm(name="General Clinic", description="General outpatient services.")
        db = _make_db(general)
        result = svc.get_maternal_healthcare_resources(db)
        assert len(result) == 1  # full list returned

    # 13. get_women_healthcare_resources filters to women resources
    def test_women_filter_returns_women_resources(self):
        svc = _svc()
        women = _make_orm(
            name="Women Health Centre",
            description="Healthcare services for women and maternity care.",
        )
        db = _make_db(women)
        result = svc.get_women_healthcare_resources(db)
        assert len(result) >= 1
        assert any("women" in r["name"].lower() or "women" in r["description"].lower()
                   for r in result)

    # 14. describe_healthcare_sources returns expected shape
    def test_describe_healthcare_sources(self):
        svc = _svc()
        info = svc.describe_healthcare_sources()
        assert "live_api_configured" in info
        assert info["live_api_configured"] is False
        assert "Healthcare" in info["categories_served"]
        assert "verified_resources" in info
        assert len(info["verified_resources"]) >= 1
        assert "note" in info

    # 15. https contact promoted to url
    def test_https_contact_promoted_to_url(self):
        svc = _svc()
        result = svc.get_healthcare_resources(_make_db(_make_orm_url()))
        assert result[0]["url"] == "https://pmc.gov.in"

    # 16. Phone contact NOT promoted to url
    def test_phone_contact_not_promoted_to_url(self):
        svc = _svc()
        result = svc.get_healthcare_resources(_make_db(_make_orm(contact="020-26128000")))
        assert result[0]["url"] == ""
        assert result[0]["contact"] == "020-26128000"


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Route tests (tests 17–20)
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthcareRoutes:

    def _routes(self):
        from app.api import routes
        return routes

    # 17. /healthcare/sources returns correct shape
    def test_healthcare_sources_endpoint(self):
        routes = self._routes()
        result = routes.healthcare_sources()
        assert isinstance(result, dict)
        assert "live_api_configured" in result
        assert "Healthcare" in result["categories_served"]

    # 18. POST /healthcare: 200 + recommendations for location-specific query
    def test_healthcare_returns_recommendations(self):
        routes = self._routes()
        from app.models.schemas import SupportRequest

        normalized = {
            "name":         "Sassoon General Hospital (B.J. Medical College)",
            "category":     "Healthcare",
            "description":  "Largest government hospital in Pune with free OPD for women.",
            "location":     "Agarkar Nagar Pune 411001",
            "contact":      "020-26128000",
            "url":          "",
            "language":     "en",
            "source":       "PostgreSQL verified data",
            "source_type":  "database",
            "last_updated": "",
            "is_live":      False,
        }

        db = MagicMock()
        with patch.object(routes, "get_all_healthcare_resources", return_value=[normalized]):
            response = routes.healthcare_recommend(
                SupportRequest(message="I need a hospital in Pune", language="en"),
                db,
            )

        assert response.intent == "healthcare"
        assert len(response.recommendations) >= 1
        top = response.recommendations[0]
        assert top.name == "Sassoon General Hospital (B.J. Medical College)"
        assert top.is_live is False
        assert top.source_type == "database"

    # 19. POST /healthcare: 503 on DB failure
    def test_healthcare_503_on_db_failure(self, monkeypatch):
        routes = self._routes()
        from app.models.schemas import SupportRequest
        from sqlalchemy.exc import SQLAlchemyError
        import json

        def fail_db(_db):
            raise SQLAlchemyError("db down")

        monkeypatch.setattr(routes, "get_all_healthcare_resources", fail_db)
        resp = routes.healthcare_recommend(
            SupportRequest(message="I need healthcare"), object()
        )
        assert resp.status_code == 503
        body = json.loads(resp.body.decode())
        assert body["error"] == "SERVICE_UNAVAILABLE"
        assert "database" not in body["message"].lower()

    # 20. POST /healthcare: 500 on pipeline failure
    def test_healthcare_500_on_pipeline_failure(self, monkeypatch):
        routes = self._routes()
        from app.models.schemas import SupportRequest
        import json

        monkeypatch.setattr(routes, "get_all_healthcare_resources", lambda _db: [])
        monkeypatch.setattr(
            routes, "run_recommendation_pipeline",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        resp = routes.healthcare_recommend(
            SupportRequest(message="I need healthcare"), object()
        )
        assert resp.status_code == 500
        body = json.loads(resp.body.decode())
        assert body["error"] == "RECOMMENDATION_ERROR"
