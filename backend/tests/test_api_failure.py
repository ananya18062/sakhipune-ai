"""test_api_failure.py — Day 29 Task 2: API Failure Testing

Covers every failure scenario required by the task spec:
  1.  Timeout                    → TIMEOUT error, DB fallback
  2.  Connection error           → CONNECTION_ERROR, DB fallback
  3.  HTTP 400                   → CLIENT_ERROR, DB fallback
  4.  HTTP 401 Unauthorized      → CLIENT_ERROR, DB fallback
  5.  HTTP 403 Forbidden         → CLIENT_ERROR, DB fallback
  6.  HTTP 404 Not Found         → CLIENT_ERROR, DB fallback
  7.  HTTP 429 Rate Limit        → CLIENT_ERROR, DB fallback
  8.  HTTP 500                   → SERVER_ERROR, DB fallback
  9.  Invalid / malformed JSON   → INVALID_JSON, DB fallback
  10. Missing required fields    → MISSING_FIELDS, DB fallback
  11. Empty API response         → empty list, no crash
  12. Unexpected response shapes → INVALID_FORMAT, DB fallback

Security:
  13. No credentials in 503 response body
  14. No stack traces in 500 response body
  15. No file paths / internal details in error messages
  16. Fallback records always marked is_live=False
  17. Live success records marked is_live=True

All tests use mocks — no live network or live database calls.
"""

from __future__ import annotations

import io
import json
import os
import sys
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.api_clients.base_client import (
    BaseAPIClient,
    ExternalAPIError,
    fetch_with_fallback,
    normalize_resources,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body


def _client(opener) -> BaseAPIClient:
    return BaseAPIClient("https://api.example.com/", opener=opener)


def _http_error(code: int) -> HTTPError:
    return HTTPError("https://api.example.com/", code, f"HTTP {code}", {}, io.BytesIO())


def _fallback_loader():
    return [{"name": "DB Resource", "category": "Employment"}]


# Named opener functions — BaseAPIClient calls opener(request, timeout=N)
# so **kwargs absorbs the keyword argument cleanly.

def _open_timeout(request, **kw):          raise TimeoutError()
def _open_urlerror(request, **kw):         raise URLError("private host: 192.168.1.1:5432")
def _open_urlerror_plain(request, **kw):   raise URLError("unreachable")

def _open_http(code: int):
    def _opener(request, **kw):
        raise _http_error(code)
    return _opener

def _open_body(body: bytes):
    def _opener(request, **kw):
        return FakeResponse(body)
    return _opener


# ─────────────────────────────────────────────────────────────────────────────
# 1. Timeout
# ─────────────────────────────────────────────────────────────────────────────

class TestTimeout:

    def test_timeout_raises_timeout_error_code(self):
        with pytest.raises(ExternalAPIError) as exc:
            _client(_open_timeout).get_json("")
        assert exc.value.code == "TIMEOUT"

    def test_timeout_public_message_is_user_friendly(self):
        with pytest.raises(ExternalAPIError) as exc:
            _client(_open_timeout).get_json("")
        assert "did not respond" in exc.value.public_message

    def test_timeout_falls_back_to_db(self):
        result = fetch_with_fallback(
            _client(_open_timeout),
            "", source="Test API", fallback_loader=_fallback_loader,
        )
        assert result[0]["name"] == "DB Resource"
        assert result[0]["is_live"] is False
        assert result[0]["source_type"] == "database"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Connection error
# ─────────────────────────────────────────────────────────────────────────────

class TestConnectionError:

    def test_urlerror_raises_connection_error_code(self):
        with pytest.raises(ExternalAPIError) as exc:
            _client(_open_urlerror_plain).get_json("")
        assert exc.value.code == "CONNECTION_ERROR"

    def test_connection_error_message_hides_internal_details(self):
        with pytest.raises(ExternalAPIError) as exc:
            _client(_open_urlerror).get_json("")
        msg = exc.value.public_message
        assert "192.168.1.1" not in msg
        assert "5432" not in msg
        assert "private" not in msg

    def test_connection_error_falls_back_to_db(self):
        result = fetch_with_fallback(
            _client(_open_urlerror_plain),
            "", source="Test API", fallback_loader=_fallback_loader,
        )
        assert result[0]["is_live"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 3–8. HTTP error codes (400, 401, 403, 404, 429, 500, 502, 503)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code,expected_error_code", [
    (400, "CLIENT_ERROR"),
    (401, "CLIENT_ERROR"),
    (403, "CLIENT_ERROR"),
    (404, "CLIENT_ERROR"),
    (429, "CLIENT_ERROR"),
    (500, "SERVER_ERROR"),
    (502, "SERVER_ERROR"),
    (503, "SERVER_ERROR"),
])
class TestHttpErrors:

    def test_http_error_raises_correct_code(self, code, expected_error_code):
        with pytest.raises(ExternalAPIError) as exc:
            _client(_open_http(code)).get_json("")
        assert exc.value.code == expected_error_code

    def test_http_error_public_message_is_user_friendly(self, code, expected_error_code):
        with pytest.raises(ExternalAPIError) as exc:
            _client(_open_http(code)).get_json("")
        msg = exc.value.public_message
        assert len(msg) > 5
        assert str(code) not in msg        # raw HTTP status not exposed to user
        assert "Traceback" not in msg
        assert "Exception" not in msg

    def test_http_error_falls_back_to_db(self, code, expected_error_code):
        result = fetch_with_fallback(
            _client(_open_http(code)),
            "", source="Test API", fallback_loader=_fallback_loader,
        )
        assert result[0]["is_live"] is False
        assert result[0]["source_type"] == "database"

    def test_http_429_rate_limit_falls_back_not_crashes(self, code, expected_error_code):
        """HTTP 429 (rate limit) must fall back gracefully, never crash."""
        if code != 429:
            pytest.skip("only for 429")
        result = fetch_with_fallback(
            _client(_open_http(429)),
            "", source="Test API", fallback_loader=_fallback_loader,
        )
        assert isinstance(result, list)
        assert result[0]["is_live"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 9. Invalid / malformed JSON
# ─────────────────────────────────────────────────────────────────────────────

class TestMalformedJson:

    def test_invalid_json_raises_invalid_json_code(self):
        with pytest.raises(ExternalAPIError) as exc:
            _client(_open_body(b"not-json{{{")).get_json("")
        assert exc.value.code == "INVALID_JSON"

    def test_invalid_json_message_is_user_friendly(self):
        with pytest.raises(ExternalAPIError) as exc:
            _client(_open_body(b"not-json")).get_json("")
        assert "invalid" in exc.value.public_message.lower()

    def test_malformed_json_falls_back_to_db(self):
        result = fetch_with_fallback(
            _client(_open_body(b"not-json{{{")),
            "", source="Test API", fallback_loader=_fallback_loader,
        )
        assert result[0]["is_live"] is False

    def test_truncated_json_falls_back_to_db(self):
        result = fetch_with_fallback(
            _client(_open_body(b'{"data": [{"name": "X", "cat')),
            "", source="Test API", fallback_loader=_fallback_loader,
        )
        assert result[0]["is_live"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 10. Missing / incomplete fields in API response
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingFields:

    def test_missing_name_field_raises_missing_fields(self):
        payload = {"data": [{"category": "Employment", "description": "A service"}]}
        with pytest.raises(ExternalAPIError) as exc:
            normalize_resources(payload, source="Test")
        assert exc.value.code == "MISSING_FIELDS"

    def test_missing_category_field_raises_missing_fields(self):
        payload = {"data": [{"name": "A Service"}]}
        with pytest.raises(ExternalAPIError) as exc:
            normalize_resources(payload, source="Test")
        assert exc.value.code == "MISSING_FIELDS"

    def test_blank_name_treated_as_missing(self):
        payload = {"data": [{"name": "   ", "category": "Employment"}]}
        with pytest.raises(ExternalAPIError) as exc:
            normalize_resources(payload, source="Test")
        assert exc.value.code == "MISSING_FIELDS"

    def test_missing_fields_in_live_response_triggers_db_fallback(self):
        bad_payload = b'{"data": [{"category": "Employment"}]}'
        result = fetch_with_fallback(
            _client(_open_body(bad_payload)),
            "", source="Test API", fallback_loader=_fallback_loader,
        )
        assert result[0]["name"] == "DB Resource"
        assert result[0]["is_live"] is False

    def test_optional_fields_default_to_empty_string(self):
        payload = {"data": [{"name": "Service", "category": "Education"}]}
        result = normalize_resources(payload, source="Test")
        assert result[0]["description"] == ""
        assert result[0]["location"] == ""
        assert result[0]["contact"] == ""
        assert result[0]["url"] == ""
        assert result[0]["last_updated"] == ""


# ─────────────────────────────────────────────────────────────────────────────
# 11. Empty response
# ─────────────────────────────────────────────────────────────────────────────

class TestEmptyResponse:

    def test_empty_data_array_returns_empty_list(self):
        result = fetch_with_fallback(
            _client(_open_body(b'{"data": []}')),
            "", source="Test API",
            fallback_loader=lambda: [{"name": "DB", "category": "Employment"}],
        )
        assert result == []

    def test_empty_list_response_normalizes_to_empty(self):
        client = _client(_open_body(b"[]"))
        result = normalize_resources(client.get_json(""), source="Test")
        assert result == []

    def test_empty_bytes_body_raises_invalid_json(self):
        with pytest.raises(ExternalAPIError) as exc:
            _client(_open_body(b"")).get_json("")
        assert exc.value.code == "INVALID_JSON"


# ─────────────────────────────────────────────────────────────────────────────
# 12. Unexpected response shapes
# ─────────────────────────────────────────────────────────────────────────────

class TestUnexpectedResponseShapes:

    def test_bare_string_falls_back_to_db(self):
        result = fetch_with_fallback(
            _client(_open_body(b'"just a string"')),
            "", source="Test API", fallback_loader=_fallback_loader,
        )
        assert result[0]["is_live"] is False

    def test_bare_integer_falls_back_to_db(self):
        result = fetch_with_fallback(
            _client(_open_body(b"42")),
            "", source="Test API", fallback_loader=_fallback_loader,
        )
        assert result[0]["is_live"] is False

    def test_dict_without_list_data_falls_back_to_db(self):
        result = fetch_with_fallback(
            _client(_open_body(b'{"data": "not a list"}')),
            "", source="Test API", fallback_loader=_fallback_loader,
        )
        assert result[0]["is_live"] is False

    def test_null_json_body_falls_back_to_db(self):
        result = fetch_with_fallback(
            _client(_open_body(b"null")),
            "", source="Test API", fallback_loader=_fallback_loader,
        )
        assert result[0]["is_live"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 13–17. Security — nothing sensitive leaks into responses or error messages
# ─────────────────────────────────────────────────────────────────────────────

class TestSecurityLeakPrevention:

    # 13. ExternalAPIError.public_message never leaks private details
    @pytest.mark.parametrize("scenario,opener", [
        ("timeout",   _open_timeout),
        ("urlerror",  _open_urlerror),
        ("http_401",  _open_http(401)),
        ("http_500",  _open_http(500)),
        ("bad_json",  _open_body(b"not-json")),
    ])
    def test_public_message_contains_no_private_data(self, scenario, opener):
        try:
            _client(opener).get_json("")
        except ExternalAPIError as exc:
            msg = exc.public_message
            assert "password" not in msg.lower()
            assert "5432" not in msg                  # DB port
            assert "secret" not in msg.lower()
            assert "Traceback" not in msg
            assert "sakhipune" not in msg.lower()
            assert "C:\\" not in msg

    # 14. Route-level 503 response body must be safe
    def test_503_route_body_contains_no_credentials(self):
        from sqlalchemy.exc import SQLAlchemyError
        from app.models.schemas import SupportRequest
        import app.api.routes as routes_mod

        def fail_db(_db):
            raise SQLAlchemyError(
                "postgresql://db_user:db_password@localhost:5432/sakhipune"
            )

        orig = routes_mod.get_all_resources
        routes_mod.get_all_resources = fail_db
        try:
            resp = routes_mod.recommend(SupportRequest(message="I need help"), object())
            body_str = resp.body.decode()
            body = json.loads(body_str)
        finally:
            routes_mod.get_all_resources = orig

        assert resp.status_code == 503
        assert "db_password" not in body_str
        assert "db_user" not in body_str
        assert "localhost" not in body_str
        assert "5432" not in body_str
        assert "Traceback" not in body_str
        assert "SQLAlchemy" not in body_str
        assert body["error"] == "SERVICE_UNAVAILABLE"

    # 15. Route-level 500 pipeline error body must be safe
    def test_500_pipeline_error_body_is_safe(self, monkeypatch):
        from app.models.schemas import SupportRequest
        import app.api.routes as routes_mod

        monkeypatch.setattr(routes_mod, "get_all_resources", lambda _db: [])
        monkeypatch.setattr(
            routes_mod, "run_recommendation_pipeline",
            lambda *a, **kw: (_ for _ in ()).throw(
                RuntimeError("SECRET_KEY=abc123 path /home/kiit/.env")
            ),
        )
        resp = routes_mod.recommend(SupportRequest(message="I need help"), object())
        body_str = resp.body.decode()

        assert resp.status_code == 500
        assert "SECRET_KEY" not in body_str
        assert "abc123" not in body_str
        assert "/home/kiit" not in body_str
        assert "Traceback" not in body_str
        assert json.loads(body_str)["error"] == "RECOMMENDATION_ERROR"

    # 16. 422 validation error body must be safe
    def test_422_body_is_safe(self):
        from app.main import request_validation_error_handler
        from fastapi import Request
        from fastapi.exceptions import RequestValidationError
        import asyncio

        request = Request({
            "type": "http", "method": "POST",
            "path": "/recommend", "headers": [],
        })
        response = asyncio.run(
            request_validation_error_handler(request, RequestValidationError([]))
        )
        body_str = response.body.decode()
        assert "Traceback" not in body_str
        assert "database" not in body_str.lower()
        assert "password" not in body_str.lower()
        assert json.loads(body_str)["error"] == "VALIDATION_ERROR"

    # 17a. Fallback records always marked is_live=False
    @pytest.mark.parametrize("opener", [
        _open_timeout,
        _open_urlerror_plain,
        _open_http(503),
        _open_body(b"not-json"),
    ])
    def test_fallback_records_always_not_live(self, opener):
        result = fetch_with_fallback(
            _client(opener),
            "", source="Test",
            fallback_loader=lambda: [{"name": "DB", "category": "Employment"}],
        )
        assert result[0]["is_live"] is False
        assert result[0]["source_type"] == "database"

    # 17b. Live success records marked is_live=True
    def test_live_success_records_marked_is_live_true(self):
        payload = b'{"data": [{"name": "Live Resource", "category": "Employment"}]}'
        result = fetch_with_fallback(
            _client(_open_body(payload)),
            "", source="Live API",
            fallback_loader=lambda: [],
        )
        assert result[0]["is_live"] is True
        assert result[0]["source_type"] == "api"
