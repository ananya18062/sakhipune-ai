"""test_legal_service.py — Tests for legal_service.py and /legal endpoints.

All external I/O is mocked.  No live network or live database required.

Coverage:
  1.  NLP: "I need legal help"                            → legal
  2.  NLP: "I need legal support"                         → legal
  3.  NLP: "Where can women get legal assistance"         → legal  (patched: assistance)
  4.  NLP: "I need help with my rights"                   → legal  (patched: rights already there)
  5.  NLP: "I need free legal advice in Pune"             → legal
  6.  Service: no resources → empty list, no crash
  7.  Service: API timeout → DB fallback, is_live=False
  8.  Service: API connection error → DB fallback
  9.  Service: malformed API response → DB fallback
  10. Service: DB fallback marks source_type=database, is_live=False
  11. Service: DV filter returns DV-relevant resources
  12. Service: DV filter falls back to full list when none match
  13. Service: women filter returns women-relevant resources
  14. Service: describe_legal_sources contains disclaimer
  15. Normalization: https contact promoted to url
  16. Normalization: phone/short contact NOT promoted to url
  17. /legal/sources endpoint returns correct shape + disclaimer
  18. /legal: 200 + recommendations for standard query
  19. /legal: 503 on DB failure
  20. /legal: 500 on pipeline failure
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
    name="Pune District Legal Services Authority (DLSA)",
    category="Legal Support",
    description="Free legal aid and advice for women and marginalised groups in Pune.",
    location="District Court Campus – Shivajinagar Pune",
    contact="https://punedlsa.org",
    language="en",
    keywords="legal,aid,free,lawyer",
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
    from app.services import legal_service
    return legal_service


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — NLP intent (tests 1–5)
# ─────────────────────────────────────────────────────────────────────────────

class TestLegalNLP:
    def test_legal_help_is_legal(self):
        assert classify_intent("I need legal help")["intent"] == "legal"

    def test_legal_support_is_legal(self):
        assert classify_intent("I need legal support")["intent"] == "legal"

    def test_women_legal_assistance_is_legal(self):
        # "assistance" added to legal keywords in patch
        r = classify_intent("Where can women get legal assistance")
        assert r["intent"] == "legal"
        assert r["confidence"] > 0

    def test_rights_help_is_legal(self):
        # "rights" already in legal keywords
        assert classify_intent("I need help with my rights")["intent"] == "legal"

    def test_free_legal_advice_is_legal(self):
        assert classify_intent("I need free legal advice in Pune")["intent"] == "legal"


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Service unit tests (tests 6–16)
# ─────────────────────────────────────────────────────────────────────────────

class TestLegalService:

    # 6. No resources → empty list, no crash
    def test_no_resources_returns_empty_list(self):
        assert _svc().get_legal_resources(_make_db()) == []

    # 7. API timeout → DB fallback
    def test_api_timeout_falls_back_to_db(self):
        svc = _svc()
        db = _make_db(_make_orm())

        def raise_timeout(req, timeout):
            raise TimeoutError()

        from app.services.api_clients.base_client import BaseAPIClient
        fake = BaseAPIClient("https://fake.example/", opener=raise_timeout)
        with patch.object(svc, "_client", fake):
            result = svc.get_legal_resources(db)

        assert result[0]["is_live"] is False
        assert result[0]["source_type"] == "database"

    # 8. API URLError → DB fallback
    def test_api_connection_failure_falls_back_to_db(self):
        svc = _svc()
        db = _make_db(_make_orm())

        def raise_url_error(req, timeout):
            raise URLError("unreachable")

        from app.services.api_clients.base_client import BaseAPIClient
        fake = BaseAPIClient("https://fake.example/", opener=raise_url_error)
        with patch.object(svc, "_client", fake):
            result = svc.get_legal_resources(db)

        assert result[0]["is_live"] is False

    # 9. Malformed API response → DB fallback
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
        fake = BaseAPIClient("https://fake.example/", opener=bad_json)
        with patch.object(svc, "_client", fake):
            result = svc.get_legal_resources(db)

        assert result[0]["is_live"] is False

    # 10. DB fallback marks correctly
    def test_db_fallback_marks_not_live(self):
        result = _svc().get_legal_resources(_make_db(_make_orm()))
        assert result[0]["is_live"] is False
        assert result[0]["source_type"] == "database"
        assert result[0]["source"] == "PostgreSQL verified data"

    # 11. DV filter returns DV-relevant resources
    def test_dv_filter_returns_dv_resources(self):
        svc = _svc()
        dv = _make_orm(
            name="Protection Officer – Domestic Violence Act",
            description="Designated officer to assist women file Domestic Incident Reports.",
        )
        general = _make_orm(name="General Legal Aid", description="General legal services.")
        result = svc.get_domestic_violence_legal_resources(_make_db(dv, general))
        names = [r["name"] for r in result]
        assert any("protection" in n.lower() or "domestic" in n.lower() for n in names)

    # 12. DV filter falls back to full list when none match
    def test_dv_filter_falls_back_to_all(self):
        svc = _svc()
        general = _make_orm(name="Tax Advisory", description="Tax guidance services.")
        result = svc.get_domestic_violence_legal_resources(_make_db(general))
        assert len(result) == 1  # full list

    # 13. Women filter returns women-relevant resources
    def test_women_filter_returns_women_resources(self):
        svc = _svc()
        women = _make_orm(
            name="Sakhi One Stop Centre",
            description="Support for women affected by violence.",
        )
        result = svc.get_women_legal_resources(_make_db(women))
        assert any("women" in r["description"].lower() for r in result)

    # 14. describe_legal_sources contains disclaimer
    def test_describe_legal_sources_has_disclaimer(self):
        info = _svc().describe_legal_sources()
        assert "live_api_configured" in info
        assert info["live_api_configured"] is False
        assert "Legal Support" in info["categories_served"]
        assert "disclaimer" in info
        assert "legal advice" in info["disclaimer"].lower()
        assert len(info["verified_resources"]) >= 1

    # 15. https contact promoted to url
    def test_https_contact_promoted_to_url(self):
        result = _svc().get_legal_resources(_make_db(_make_orm(contact="https://punedlsa.org")))
        assert result[0]["url"] == "https://punedlsa.org"

    # 16. Short code (181) NOT promoted to url
    def test_short_contact_not_promoted_to_url(self):
        result = _svc().get_legal_resources(_make_db(_make_orm(contact="181")))
        assert result[0]["url"] == ""
        assert result[0]["contact"] == "181"


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Route tests (tests 17–20)
# ─────────────────────────────────────────────────────────────────────────────

class TestLegalRoutes:

    def _routes(self):
        from app.api import routes
        return routes

    # 17. /legal/sources returns correct shape + disclaimer
    def test_legal_sources_endpoint(self):
        result = self._routes().legal_sources()
        assert isinstance(result, dict)
        assert "Legal Support" in result["categories_served"]
        assert "disclaimer" in result
        assert "live_api_configured" in result

    # 18. POST /legal: 200 + recommendations
    def test_legal_returns_recommendations(self):
        routes = self._routes()
        from app.models.schemas import SupportRequest

        normalized = {
            "name":         "Pune District Legal Services Authority (DLSA)",
            "category":     "Legal Support",
            "description":  "Free legal aid for women in Pune.",
            "location":     "District Court Campus – Shivajinagar Pune",
            "contact":      "https://punedlsa.org",
            "url":          "https://punedlsa.org",
            "language":     "en",
            "source":       "PostgreSQL verified data",
            "source_type":  "database",
            "last_updated": "",
            "is_live":      False,
        }

        db = MagicMock()
        with patch.object(routes, "get_all_legal_resources", return_value=[normalized]):
            response = routes.legal_recommend(
                SupportRequest(message="I need legal help", language="en"), db
            )

        assert response.intent == "legal"
        assert len(response.recommendations) >= 1
        top = response.recommendations[0]
        assert top.name == "Pune District Legal Services Authority (DLSA)"
        assert top.is_live is False
        assert top.url == "https://punedlsa.org"

    # 19. POST /legal: 503 on DB failure
    def test_legal_503_on_db_failure(self, monkeypatch):
        routes = self._routes()
        from app.models.schemas import SupportRequest
        from sqlalchemy.exc import SQLAlchemyError
        import json

        monkeypatch.setattr(routes, "get_all_legal_resources",
                            lambda _db: (_ for _ in ()).throw(SQLAlchemyError("down")))
        resp = routes.legal_recommend(SupportRequest(message="I need legal help"), object())
        assert resp.status_code == 503
        body = json.loads(resp.body.decode())
        assert body["error"] == "SERVICE_UNAVAILABLE"

    # 20. POST /legal: 500 on pipeline failure
    def test_legal_500_on_pipeline_failure(self, monkeypatch):
        routes = self._routes()
        from app.models.schemas import SupportRequest
        import json

        monkeypatch.setattr(routes, "get_all_legal_resources", lambda _db: [])
        monkeypatch.setattr(
            routes, "run_recommendation_pipeline",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        resp = routes.legal_recommend(SupportRequest(message="I need legal help"), object())
        assert resp.status_code == 500
        body = json.loads(resp.body.decode())
        assert body["error"] == "RECOMMENDATION_ERROR"
