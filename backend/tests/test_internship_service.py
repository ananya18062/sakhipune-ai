"""test_internship_service.py — Tests for internship_service.py and /internships endpoints.

All external I/O is mocked.  No live network or live database required for these tests.

Coverage:
  1.  NLP: "I am looking for internships"                      → employment intent
  2.  NLP: "I need a technology internship"                    → employment intent
  3.  NLP: "I want a software internship in Pune"              → employment intent
  4.  NLP: screenshot query with preferences                   → employment intent
  5.  NLP: "Are there internships for women"                   → employment intent
  6.  Service: no resources → empty list, no crash
  7.  Service: API timeout  → DB fallback, is_live=False
  8.  Service: API failure (URLError) → DB fallback
  9.  Service: malformed API response → DB fallback
  10. Service: DB fallback marks records source_type=database, is_live=False
  11. Service: technology preference filters SARTHI to top
  12. Service: women preference filters SARTHI to top
  13. Service: unknown preference → returns full list (soft filter)
  14. Service: get_technology_internship_resources returns tech resources
  15. Service: get_women_internship_resources returns women resources
  16. Service: describe_internship_sources returns expected shape
  17. Normalization: https contact promoted to url field
  18. /internships/sources endpoint returns correct shape
  19. /internships: 200 + recommendations for the screenshot query
  20. /internships: 503 on DB failure, 500 on pipeline failure
"""

from __future__ import annotations

import io
import os
import sys
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.nlp_service import classify_intent


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_orm(
    name="SARTHI COEP Technical Internship for Women",
    category="Internships",
    description="SARTHI runs advanced technical training programmes at COEP Pune for women.",
    location="College of Engineering Pune (COEP) – Shivajinagar Pune",
    contact="https://sarthi.maharashtra.gov.in",
    language="en",
    keywords="internship,technical,COEP,women",
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


def _make_db(*resources):
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value = q
    q.order_by.return_value = q
    q.all.return_value = list(resources)
    return db


def _svc():
    from app.services import internship_service
    return internship_service


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — NLP intent (tests 1–5)
# ─────────────────────────────────────────────────────────────────────────────

class TestInternshipNLP:
    def test_looking_for_internships_is_employment(self):
        r = classify_intent("I am looking for internships")
        assert r["intent"] == "employment"
        assert r["confidence"] > 0

    def test_technology_internship_is_employment(self):
        r = classify_intent("I need a technology internship")
        assert r["intent"] == "employment"
        assert r["confidence"] > 0

    def test_software_internship_pune_is_employment(self):
        r = classify_intent("I want a software internship in Pune")
        assert r["intent"] == "employment"
        assert r["confidence"] > 0

    def test_screenshot_query_is_employment(self):
        q = "I am looking for internships. My preferences are: Technology, Some experience, Open to options."
        r = classify_intent(q)
        assert r["intent"] == "employment"
        assert r["confidence"] > 0

    def test_internships_for_women_is_employment(self):
        r = classify_intent("Are there internships for women")
        assert r["intent"] == "employment"
        assert r["confidence"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Service unit tests (tests 6–17)
# ─────────────────────────────────────────────────────────────────────────────

class TestInternshipService:

    # 6. No resources → empty list, no crash
    def test_no_resources_returns_empty_list(self):
        svc = _svc()
        result = svc.get_internship_resources(_make_db())
        assert result == []

    # 7. API timeout → DB fallback
    def test_api_timeout_falls_back_to_db(self):
        svc = _svc()
        resource = _make_orm()
        db = _make_db(resource)

        def raise_timeout(req, timeout):
            raise TimeoutError()

        from app.services.api_clients.base_client import BaseAPIClient
        fake_client = BaseAPIClient("https://fake.example/", opener=raise_timeout)

        with patch.object(svc, "_client", fake_client):
            result = svc.get_internship_resources(db)

        assert len(result) == 1
        assert result[0]["is_live"] is False
        assert result[0]["source_type"] == "database"

    # 8. API URLError → DB fallback
    def test_api_connection_failure_falls_back_to_db(self):
        svc = _svc()
        resource = _make_orm()
        db = _make_db(resource)

        def raise_url_error(req, timeout):
            raise URLError("unreachable")

        from app.services.api_clients.base_client import BaseAPIClient
        fake_client = BaseAPIClient("https://fake.example/", opener=raise_url_error)

        with patch.object(svc, "_client", fake_client):
            result = svc.get_internship_resources(db)

        assert len(result) == 1
        assert result[0]["is_live"] is False

    # 9. Malformed API response → DB fallback
    def test_malformed_api_response_falls_back_to_db(self):
        svc = _svc()
        resource = _make_orm()
        db = _make_db(resource)

        def bad_json(req, timeout):
            class R:
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def read(self): return b"not-json{"
            return R()

        from app.services.api_clients.base_client import BaseAPIClient
        fake_client = BaseAPIClient("https://fake.example/", opener=bad_json)

        with patch.object(svc, "_client", fake_client):
            result = svc.get_internship_resources(db)

        assert len(result) == 1
        assert result[0]["is_live"] is False

    # 10. DB fallback marks records correctly
    def test_db_fallback_marks_not_live(self):
        svc = _svc()
        result = svc.get_internship_resources(_make_db(_make_orm()))
        assert result[0]["is_live"] is False
        assert result[0]["source_type"] == "database"
        assert result[0]["source"] == "PostgreSQL verified data"

    # 11. Technology preference filters to tech resources
    def test_technology_preference_filters_tech_resources(self):
        svc = _svc()
        tech = _make_orm(
            name="SARTHI COEP Technical Internship",
            description="Technical training at COEP Pune.",
        )
        general = _make_orm(
            name="General Business Internship",
            description="Business support and administration.",
        )
        db = _make_db(tech, general)
        result = svc.get_internship_resources(
            db, preferences={"interest_area": "Technology"}
        )
        names = [r["name"] for r in result]
        assert any("technical" in n.lower() or "sarthi" in n.lower() for n in names)

    # 12. Women preference filters to women-relevant resources
    def test_women_preference_surfaces_women_resources(self):
        svc = _svc()
        women = _make_orm(
            name="SARTHI COEP Technical Internship for Women",
            description="Programme for women from target communities.",
        )
        db = _make_db(women)
        result = svc.get_women_internship_resources(db)
        assert len(result) >= 1
        assert any("women" in r["name"].lower() or "women" in r["description"].lower()
                   for r in result)

    # 13. Unknown preference → soft filter returns full list
    def test_unknown_preference_returns_full_list(self):
        svc = _svc()
        r1 = _make_orm(name="Resource A")
        r2 = _make_orm(name="Resource B")
        db = _make_db(r1, r2)
        result = svc.get_internship_resources(
            db, preferences={"interest_area": "Underwater Basket Weaving"}
        )
        assert len(result) == 2  # soft filter → returned full list

    # 14. get_technology_internship_resources returns tech resources
    def test_get_technology_internship_resources(self):
        svc = _svc()
        tech = _make_orm(
            name="SARTHI Technical Internship",
            description="Advanced technical programme at COEP.",
        )
        db = _make_db(tech)
        result = svc.get_technology_internship_resources(db)
        assert len(result) >= 1

    # 15. get_women_internship_resources returns women resources
    def test_get_women_internship_resources(self):
        svc = _svc()
        women = _make_orm(
            name="SARTHI COEP Technical Internship for Women",
            description="For women from target communities.",
        )
        db = _make_db(women)
        result = svc.get_women_internship_resources(db)
        assert len(result) >= 1

    # 16. describe_internship_sources returns expected fields
    def test_describe_internship_sources(self):
        svc = _svc()
        info = svc.describe_internship_sources()
        assert "live_api_configured" in info
        assert info["live_api_configured"] is False
        assert "Internships" in info["categories_served"]
        assert "preference_fields_supported" in info
        assert "interest_area" in info["preference_fields_supported"]
        assert "note" in info

    # 17. https contact is promoted to url field
    def test_https_contact_promoted_to_url(self):
        svc = _svc()
        resource = _make_orm(contact="https://sarthi.maharashtra.gov.in")
        result = svc.get_internship_resources(_make_db(resource))
        assert result[0]["url"] == "https://sarthi.maharashtra.gov.in"
        # contact is also preserved
        assert result[0]["contact"] == "https://sarthi.maharashtra.gov.in"


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Route tests (tests 18–20)
# ─────────────────────────────────────────────────────────────────────────────

class TestInternshipRoutes:

    def _routes(self):
        from app.api import routes
        return routes

    # 18. /internships/sources returns correct shape
    def test_internships_sources_endpoint(self):
        routes = self._routes()
        result = routes.internships_sources()
        assert isinstance(result, dict)
        assert "live_api_configured" in result
        assert "Internships" in result["categories_served"]
        assert "preference_fields_supported" in result

    # 19. POST /internships: screenshot query returns recommendations
    def test_screenshot_query_returns_recommendations(self):
        routes = self._routes()
        from app.models.schemas import SupportRequest

        normalized_resource = {
            "name":         "SARTHI COEP Technical Internship for Women",
            "category":     "Internships",
            "description":  "SARTHI runs advanced technical training at COEP Pune for women.",
            "location":     "College of Engineering Pune (COEP) – Shivajinagar Pune",
            "contact":      "https://sarthi.maharashtra.gov.in",
            "url":          "https://sarthi.maharashtra.gov.in",
            "language":     "en",
            "source":       "PostgreSQL verified data",
            "source_type":  "database",
            "last_updated": "",
            "is_live":      False,
        }

        db = MagicMock()
        with patch.object(routes, "get_all_internship_resources",
                          return_value=[normalized_resource]):
            response = routes.internships_recommend(
                SupportRequest(
                    message=(
                        "I am looking for internships. "
                        "My preferences are: Technology, Some experience, Open to options."
                    ),
                    category="internships",
                    preferences={
                        "interest_area": "Technology",
                        "experience_level": "Some experience",
                        "work_type": "Open to options",
                    },
                    language="en",
                ),
                db,
            )

        assert response.intent == "employment"
        assert len(response.recommendations) >= 1
        top = response.recommendations[0]
        assert top.name == "SARTHI COEP Technical Internship for Women"
        assert top.is_live is False
        assert top.source_type == "database"
        assert top.url == "https://sarthi.maharashtra.gov.in"

    # 20a. POST /internships: 503 on DB failure
    def test_internships_503_on_db_failure(self, monkeypatch):
        routes = self._routes()
        from app.models.schemas import SupportRequest
        from sqlalchemy.exc import SQLAlchemyError
        import json

        def fail_db(_db, **_kw):
            raise SQLAlchemyError("db down")

        monkeypatch.setattr(routes, "get_all_internship_resources", fail_db)
        resp = routes.internships_recommend(
            SupportRequest(message="I want an internship"), object()
        )
        assert resp.status_code == 503
        body = json.loads(resp.body.decode())
        assert body["error"] == "SERVICE_UNAVAILABLE"

    # 20b. POST /internships: 500 on pipeline failure
    def test_internships_500_on_pipeline_failure(self, monkeypatch):
        routes = self._routes()
        from app.models.schemas import SupportRequest
        import json

        monkeypatch.setattr(routes, "get_all_internship_resources",
                            lambda _db, **_kw: [])
        monkeypatch.setattr(
            routes, "run_recommendation_pipeline",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        resp = routes.internships_recommend(
            SupportRequest(message="I want an internship"), object()
        )
        assert resp.status_code == 500
        body = json.loads(resp.body.decode())
        assert body["error"] == "RECOMMENDATION_ERROR"
