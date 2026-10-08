"""test_financial_service.py — Tests for financial_service.py and /financial endpoints.

All external I/O is mocked.  No live network or database required.

Coverage:
  1.  NLP: "I need financial help"               → financial_support
  2.  NLP: "I need financial support"            → financial_support
  3.  NLP: "I need money assistance"             → financial_support
  4.  NLP: "I need livelihood support"           → financial_support  (was MISS before patch)
  5.  NLP: "I need help paying my bills"         → financial_support  (was MISS before patch)
  6.  Service: no resources → empty list, no crash
  7.  Service: API timeout → DB fallback, is_live=False
  8.  Service: API connection error → DB fallback
  9.  Service: malformed API response → DB fallback
  10. Service: DB fallback marks source_type=database, is_live=False
  11. Service: get_women_financial_resources filters correctly
  12. Service: get_women_financial_resources falls back to full list
  13. Service: get_livelihood_resources filters correctly
  14. Service: describe_financial_sources returns expected shape
  15. Normalization: https contact promoted to url
  16. Normalization: non-https contact NOT promoted to url
  17. /financial/sources endpoint returns correct shape
  18. /financial: 200 + recommendations for standard query
  19. /financial: 503 on DB failure
  20. /financial: 500 on pipeline failure
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
    name="PM Jan Dhan Yojana – Women's Bank Account",
    category="Financial Support",
    description="Government scheme providing zero-balance bank accounts to unbanked women.",
    location="Nationalised Banks – Pune",
    contact="https://pmjdy.gov.in",
    language="en",
    keywords="bank,account,women,financial",
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
    from app.services import financial_service
    return financial_service


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — NLP (tests 1–5)
# ─────────────────────────────────────────────────────────────────────────────

class TestFinancialNLP:
    def test_financial_help_is_financial_support(self):
        assert classify_intent("I need financial help")["intent"] == "financial_support"

    def test_financial_support_is_financial_support(self):
        assert classify_intent("I need financial support")["intent"] == "financial_support"

    def test_money_assistance_is_financial_support(self):
        assert classify_intent("I need money assistance")["intent"] == "financial_support"

    def test_livelihood_support_is_financial_support(self):
        # Was MISS (general) before NLP patch
        r = classify_intent("I need livelihood support")
        assert r["intent"] == "financial_support"
        assert r["confidence"] > 0

    def test_paying_bills_is_financial_support(self):
        # Was MISS (general) before NLP patch
        r = classify_intent("I need help paying my bills")
        assert r["intent"] == "financial_support"
        assert r["confidence"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Service unit tests (tests 6–16)
# ─────────────────────────────────────────────────────────────────────────────

class TestFinancialService:

    # 6. No resources → empty list, no crash
    def test_no_resources_returns_empty_list(self):
        assert _svc().get_financial_resources(_make_db()) == []

    # 7. API timeout → DB fallback, is_live=False
    def test_api_timeout_falls_back_to_db(self):
        svc = _svc()
        db = _make_db(_make_orm())

        def raise_timeout(req, timeout):
            raise TimeoutError()

        from app.services.api_clients.base_client import BaseAPIClient
        fake = BaseAPIClient("https://fake.example/", opener=raise_timeout)
        with patch.object(svc, "_client", fake):
            result = svc.get_financial_resources(db)

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
            result = svc.get_financial_resources(db)

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
            result = svc.get_financial_resources(db)

        assert result[0]["is_live"] is False

    # 10. DB fallback marks correctly
    def test_db_fallback_marks_not_live(self):
        result = _svc().get_financial_resources(_make_db(_make_orm()))
        assert result[0]["is_live"] is False
        assert result[0]["source_type"] == "database"
        assert result[0]["source"] == "PostgreSQL verified data"

    # 11. get_women_financial_resources filters correctly
    def test_women_filter_returns_women_resources(self):
        svc = _svc()
        women = _make_orm(
            name="Mukhyamantri Majhi Ladki Bahin – Financial Aid",
            description="Monthly transfer to eligible women in Maharashtra.",
        )
        general = _make_orm(name="Generic Finance", description="General finance services.")
        result = svc.get_women_financial_resources(_make_db(women, general))
        names = [r["name"] for r in result]
        assert any("ladki" in n.lower() or "women" in r["description"].lower()
                   for n, r in zip(names, result))

    # 12. get_women_financial_resources falls back to full list
    def test_women_filter_falls_back_to_all(self):
        svc = _svc()
        general = _make_orm(name="Generic Scheme", description="Generic financial scheme.")
        result = svc.get_women_financial_resources(_make_db(general))
        assert len(result) == 1

    # 13. get_livelihood_resources filters correctly
    def test_livelihood_filter_returns_livelihood_resources(self):
        svc = _svc()
        livelihood = _make_orm(
            name="DAY-NULM Micro-credit Support",
            description="Micro-loans and financial linkages for urban poor women through SHG.",
        )
        other = _make_orm(name="Bank Account Scheme", description="Zero balance bank account.")
        result = svc.get_livelihood_resources(_make_db(livelihood, other))
        names = [r["name"] for r in result]
        assert any("nulm" in n.lower() or "micro" in r["description"].lower()
                   for n, r in zip(names, result))

    # 14. describe_financial_sources returns expected shape
    def test_describe_financial_sources(self):
        info = _svc().describe_financial_sources()
        assert "live_api_configured" in info
        assert info["live_api_configured"] is False
        assert "Financial Support" in info["categories_served"]
        assert len(info["verified_resources"]) >= 1
        assert "note" in info

    # 15. https contact promoted to url
    def test_https_contact_promoted_to_url(self):
        result = _svc().get_financial_resources(_make_db(_make_orm(contact="https://pmjdy.gov.in")))
        assert result[0]["url"] == "https://pmjdy.gov.in"

    # 16. Non-https contact NOT promoted to url
    def test_non_https_contact_not_promoted_to_url(self):
        result = _svc().get_financial_resources(_make_db(_make_orm(contact="1800-11-0001")))
        assert result[0]["url"] == ""
        assert result[0]["contact"] == "1800-11-0001"


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Route tests (tests 17–20)
# ─────────────────────────────────────────────────────────────────────────────

class TestFinancialRoutes:

    def _routes(self):
        from app.api import routes
        return routes

    # 17. /financial/sources returns correct shape
    def test_financial_sources_endpoint(self):
        result = self._routes().financial_sources()
        assert isinstance(result, dict)
        assert "Financial Support" in result["categories_served"]
        assert "live_api_configured" in result

    # 18. POST /financial: 200 + recommendations
    def test_financial_returns_recommendations(self):
        routes = self._routes()
        from app.models.schemas import SupportRequest

        normalized = {
            "name":         "PM Jan Dhan Yojana – Women's Bank Account",
            "category":     "Financial Support",
            "description":  "Zero-balance bank account for unbanked women.",
            "location":     "Nationalised Banks – Pune",
            "contact":      "https://pmjdy.gov.in",
            "url":          "https://pmjdy.gov.in",
            "language":     "en",
            "source":       "PostgreSQL verified data",
            "source_type":  "database",
            "last_updated": "",
            "is_live":      False,
        }

        db = MagicMock()
        with patch.object(routes, "get_all_financial_resources", return_value=[normalized]):
            response = routes.financial_recommend(
                SupportRequest(message="I need financial help", language="en"), db
            )

        assert response.intent == "financial_support"
        assert len(response.recommendations) >= 1
        top = response.recommendations[0]
        assert top.name == "PM Jan Dhan Yojana – Women's Bank Account"
        assert top.is_live is False
        assert top.url == "https://pmjdy.gov.in"

    # 19. POST /financial: 503 on DB failure
    def test_financial_503_on_db_failure(self, monkeypatch):
        routes = self._routes()
        from app.models.schemas import SupportRequest
        from sqlalchemy.exc import SQLAlchemyError
        import json

        monkeypatch.setattr(routes, "get_all_financial_resources",
                            lambda _db: (_ for _ in ()).throw(SQLAlchemyError("down")))
        resp = routes.financial_recommend(
            SupportRequest(message="I need financial help"), object()
        )
        assert resp.status_code == 503
        body = json.loads(resp.body.decode())
        assert body["error"] == "SERVICE_UNAVAILABLE"

    # 20. POST /financial: 500 on pipeline failure
    def test_financial_500_on_pipeline_failure(self, monkeypatch):
        routes = self._routes()
        from app.models.schemas import SupportRequest
        import json

        monkeypatch.setattr(routes, "get_all_financial_resources", lambda _db: [])
        monkeypatch.setattr(
            routes, "run_recommendation_pipeline",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        resp = routes.financial_recommend(
            SupportRequest(message="I need financial help"), object()
        )
        assert resp.status_code == 500
        body = json.loads(resp.body.decode())
        assert body["error"] == "RECOMMENDATION_ERROR"
