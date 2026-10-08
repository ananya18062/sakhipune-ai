"""test_jobs_service.py — Tests for jobs_service.py and the /jobs endpoints.

All external I/O is mocked.  No live network calls, no live database required
for the unit tests.  Integration tests (marked with the db fixture) use
the real PostgreSQL instance when available.

Coverage:
  1.  NLP: "I need a job in Pune"            → employment intent
  2.  NLP: "I am looking for employment opportunities" → employment intent
  3.  NLP: "I want a job for women"          → employment intent
  4.  NLP: entry-level job query             → employment intent
  5.  NLP: location-specific job query       → employment intent
  6.  Service: no resources → empty list, no crash
  7.  Service: API timeout  → falls back to DB data, is_live=False
  8.  Service: API failure (URLError) → falls back to DB data
  9.  Service: malformed API response → falls back to DB data
  10. Service: PostgreSQL fallback marks records is_live=False
  11. Service: get_women_job_resources filters correctly
  12. Service: describe_job_sources returns expected shape
  13. Normalization: orm row → NormalizedResource dict fields
  14. Normalization: https contact promoted to url field
  15. Normalization: non-https contact not promoted to url
  16. /jobs/sources endpoint returns correct structure
  17. /jobs endpoint: 200 + recommendations for valid request
  18. /jobs endpoint: 422 on empty message
  19. /jobs endpoint: 503 when DB raises SQLAlchemyError
  20. /jobs endpoint: 500 when pipeline raises unexpected error
"""

from __future__ import annotations

import io
import os
import sys
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.api_clients.base_client import ExternalAPIError, NormalizedResource
from app.services.nlp_service import classify_intent


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_orm_resource(
    name="Mahaswayam Employment Centre",
    category="Employment",
    description="Government employment guidance centre in Pune.",
    location="481 Rasta Peth, Pune 411011",
    contact="https://mahaswayam.gov.in",
    language="en",
    keywords="job,employment,career",
):
    """Return a lightweight mock that mimics a SupportResource ORM object."""
    r = MagicMock()
    r.id          = 1
    r.name        = name
    r.category    = category
    r.description = description
    r.location    = location
    r.contact     = contact
    r.language    = language
    r.keywords    = keywords
    return r


def _make_db_with_resources(*resources):
    """Return a mock Session whose query chain returns the given resources."""
    db = MagicMock()
    q  = db.query.return_value
    q.filter.return_value         = q
    q.order_by.return_value       = q
    q.all.return_value            = list(resources)
    return db


def _make_empty_db():
    return _make_db_with_resources()


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — NLP intent checks (tests 1–5)
# ─────────────────────────────────────────────────────────────────────────────

class TestEmploymentNLP:
    def test_job_in_pune_is_employment(self):
        result = classify_intent("I need a job in Pune")
        assert result["intent"] == "employment"
        assert result["confidence"] > 0

    def test_employment_opportunities_is_employment(self):
        result = classify_intent("I am looking for employment opportunities")
        assert result["intent"] == "employment"
        assert result["confidence"] > 0

    def test_job_for_women_is_employment(self):
        result = classify_intent("I want a job for women")
        assert result["intent"] == "employment"
        assert result["confidence"] > 0

    def test_entry_level_jobs_is_employment(self):
        result = classify_intent("I am searching for entry level jobs")
        assert result["intent"] == "employment"
        assert result["confidence"] > 0

    def test_location_specific_job_is_employment(self):
        result = classify_intent("Are there job vacancies available in Pune for women")
        assert result["intent"] == "employment"
        assert result["confidence"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — jobs_service unit tests (tests 6–15)
# ─────────────────────────────────────────────────────────────────────────────

class TestJobsService:

    # ── Import inside test methods to avoid module-level side-effects ──────

    def _service(self):
        from app.services import jobs_service
        return jobs_service

    # 6. No resources in DB → empty list, no crash
    def test_no_resources_returns_empty_list(self):
        svc = self._service()
        db  = _make_empty_db()
        result = svc.get_job_resources(db)
        assert result == []

    # 7. API timeout → falls back to DB
    def test_api_timeout_falls_back_to_db(self):
        svc = self._service()
        resource = _make_orm_resource()
        db = _make_db_with_resources(resource)

        def raise_timeout(req, timeout):
            raise TimeoutError()

        # Temporarily inject a client pointing at a fake URL
        from app.services.api_clients.base_client import BaseAPIClient
        fake_client = BaseAPIClient("https://fake-jobs-api.example/", opener=raise_timeout)

        with patch.object(svc, "_client", fake_client):
            result = svc.get_job_resources(db)

        assert len(result) == 1
        assert result[0]["name"] == resource.name
        assert result[0]["is_live"] is False
        assert result[0]["source_type"] == "database"

    # 8. API URLError → falls back to DB
    def test_api_connection_failure_falls_back_to_db(self):
        svc = self._service()
        resource = _make_orm_resource()
        db = _make_db_with_resources(resource)

        def raise_url_error(req, timeout):
            raise URLError("network failure")

        from app.services.api_clients.base_client import BaseAPIClient
        fake_client = BaseAPIClient("https://fake-jobs-api.example/", opener=raise_url_error)

        with patch.object(svc, "_client", fake_client):
            result = svc.get_job_resources(db)

        assert len(result) == 1
        assert result[0]["is_live"] is False

    # 9. Malformed API response → falls back to DB
    def test_malformed_api_response_falls_back_to_db(self):
        svc = self._service()
        resource = _make_orm_resource()
        db = _make_db_with_resources(resource)

        def return_bad_json(req, timeout):
            class Resp:
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def read(self): return b"not-valid-json{"
            return Resp()

        from app.services.api_clients.base_client import BaseAPIClient
        fake_client = BaseAPIClient("https://fake-jobs-api.example/", opener=return_bad_json)

        with patch.object(svc, "_client", fake_client):
            result = svc.get_job_resources(db)

        assert len(result) == 1
        assert result[0]["is_live"] is False

    # 10. PostgreSQL fallback marks records is_live=False and source_type=database
    def test_db_fallback_marks_records_not_live(self):
        svc = self._service()
        resource = _make_orm_resource()
        db = _make_db_with_resources(resource)

        result = svc.get_job_resources(db)

        assert result[0]["is_live"] is False
        assert result[0]["source_type"] == "database"
        assert result[0]["source"] == "PostgreSQL verified data"

    # 11. get_women_job_resources filters to women-relevant resources
    def test_women_job_resources_filters_correctly(self):
        svc = self._service()
        women_resource  = _make_orm_resource(
            name="SARTHI Skill Development Programme for Women",
            description="Free skill training for women in Pune.",
        )
        general_resource = _make_orm_resource(
            name="Generic Resource",
            description="General support services.",
        )
        db = _make_db_with_resources(women_resource, general_resource)

        result = svc.get_women_job_resources(db)

        # SARTHI contains "women" → should be in filtered list
        names = [r["name"] for r in result]
        assert "SARTHI Skill Development Programme for Women" in names

    # 11b. When no women-specific resources exist, returns all (no empty result)
    def test_women_job_resources_falls_back_to_all_when_no_match(self):
        svc = self._service()
        general = _make_orm_resource(name="Generic Centre", description="General support.")
        db = _make_db_with_resources(general)

        result = svc.get_women_job_resources(db)
        assert len(result) == 1  # fell back to full list

    # 12. describe_job_sources returns expected structure
    def test_describe_job_sources_structure(self):
        svc = self._service()
        info = svc.describe_job_sources()

        assert "live_api_configured" in info
        assert "fallback" in info
        assert "categories_served" in info
        assert "Employment" in info["categories_served"]
        assert "note" in info
        assert info["live_api_configured"] is False  # no JOBS_API_URL set

    # 13. ORM row → NormalizedResource dict has all required fields
    def test_orm_to_normalized_has_all_fields(self):
        svc = self._service()
        resource = _make_orm_resource()
        db = _make_db_with_resources(resource)

        result = svc.get_job_resources(db)
        assert len(result) == 1
        rec = result[0]

        required_fields = {"name", "category", "description", "location",
                           "contact", "url", "language", "source",
                           "source_type", "last_updated", "is_live"}
        assert required_fields.issubset(rec.keys())

    # 14. https contact is promoted to url field
    def test_https_contact_promoted_to_url(self):
        svc = self._service()
        resource = _make_orm_resource(contact="https://mahaswayam.gov.in")
        db = _make_db_with_resources(resource)

        result = svc.get_job_resources(db)
        assert result[0]["url"] == "https://mahaswayam.gov.in"

    # 15. Non-https contact is not promoted to url
    def test_non_https_contact_not_promoted_to_url(self):
        svc = self._service()
        resource = _make_orm_resource(contact="020-26128000")
        db = _make_db_with_resources(resource)

        result = svc.get_job_resources(db)
        assert result[0]["url"] == ""


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — /jobs route tests (tests 16–20)
# ─────────────────────────────────────────────────────────────────────────────

class TestJobsRoutes:

    def _import_routes(self):
        from app.api import routes
        return routes

    # 16. /jobs/sources returns correct structure
    def test_jobs_sources_endpoint_structure(self):
        routes = self._import_routes()
        result = routes.jobs_sources()

        assert isinstance(result, dict)
        assert "live_api_configured" in result
        assert "categories_served" in result
        assert "Employment" in result["categories_served"]

    # 17. POST /jobs returns 200 + recommendations for valid request
    def test_jobs_endpoint_returns_recommendations(self):
        routes = self._import_routes()
        from app.models.schemas import SupportRequest

        resource = _make_orm_resource()
        db = _make_db_with_resources(resource)

        with patch.object(routes, "get_all_employment_resources",
                          return_value=[{
                              "name":        resource.name,
                              "category":    resource.category,
                              "description": resource.description,
                              "location":    resource.location,
                              "contact":     resource.contact,
                              "url":         resource.contact,
                              "language":    resource.language,
                              "source":      "PostgreSQL verified data",
                              "source_type": "database",
                              "last_updated": "",
                              "is_live":     False,
                          }]):
            response = routes.jobs_recommend(
                SupportRequest(message="I need a job in Pune", language="en"),
                db,
            )

        assert response.intent == "employment"
        assert isinstance(response.recommendations, list)
        assert len(response.recommendations) >= 1
        assert response.recommendations[0].name == resource.name

    # 18. POST /jobs returns 422 on empty message (Pydantic validation)
    def test_jobs_endpoint_rejects_empty_message(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            from app.models.schemas import SupportRequest
            SupportRequest(message="   ")

    # 19. POST /jobs returns 503 when DB raises SQLAlchemyError
    def test_jobs_endpoint_returns_503_on_db_failure(self, monkeypatch):
        routes = self._import_routes()
        from app.models.schemas import SupportRequest
        from sqlalchemy.exc import SQLAlchemyError
        import json

        def fail_db(_db):
            raise SQLAlchemyError("db is down")

        monkeypatch.setattr(routes, "get_all_employment_resources", fail_db)
        response = routes.jobs_recommend(
            SupportRequest(message="I need a job"), object()
        )

        assert response.status_code == 503
        body = json.loads(response.body.decode())
        assert body["error"] == "SERVICE_UNAVAILABLE"
        assert "database" not in body["message"].lower()

    # 20. POST /jobs returns 500 when pipeline raises unexpected error
    def test_jobs_endpoint_returns_500_on_pipeline_failure(self, monkeypatch):
        routes = self._import_routes()
        from app.models.schemas import SupportRequest
        import json

        monkeypatch.setattr(routes, "get_all_employment_resources", lambda _db: [])
        monkeypatch.setattr(routes, "run_recommendation_pipeline",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))

        # pipeline raises → 500
        response = routes.jobs_recommend(
            SupportRequest(message="I need a job"), object()
        )

        assert response.status_code == 500
        body = json.loads(response.body.decode())
        assert body["error"] == "RECOMMENDATION_ERROR"
