"""Tests for the API client infrastructure.

All tests use mocked transport — no live network calls are made.
Coverage:
  - Successful GET + normalization
  - Timeout (ExternalAPIError TIMEOUT)
  - Connection / URLError (ExternalAPIError CONNECTION_ERROR)
  - 4xx HTTP error (ExternalAPIError CLIENT_ERROR)
  - 5xx HTTP error (ExternalAPIError SERVER_ERROR)
  - Malformed / non-JSON response (ExternalAPIError INVALID_JSON)
  - Bare-string / unexpected top-level response type (ExternalAPIError INVALID_FORMAT)
  - Missing required fields — name absent (ExternalAPIError MISSING_FIELDS)
  - Missing required fields — category absent (ExternalAPIError MISSING_FIELDS)
  - Fallback: external failure → database records returned as non-live
  - NormalizedResource.as_dict() round-trip
  - normalize_resource source_type validation
  - fetch_with_fallback: live path succeeds without touching fallback
  - Empty data list is accepted (returns empty list, no error)
"""

import io
import os
import sys
from urllib.error import HTTPError, URLError

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.api_clients.base_client import (
    BaseAPIClient,
    ExternalAPIError,
    NormalizedResource,
    fetch_with_fallback,
    normalize_resource,
    normalize_resources,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

class FakeResponse:
    """Minimal file-like object that satisfies urlopen's context-manager protocol."""

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self._body


def make_client(opener) -> BaseAPIClient:
    return BaseAPIClient("https://verified.example/", opener=opener)


def valid_payload() -> bytes:
    return b'{"data": [{"name": "Support Centre", "category": "Education", "description": "Guidance for women"}]}'


def make_http_error(status_code: int, url: str = "https://verified.example/") -> HTTPError:
    return HTTPError(url, status_code, f"HTTP {status_code}", {}, io.BytesIO())


# ── Success path ──────────────────────────────────────────────────────────────

def test_successful_response_is_normalized():
    client = make_client(lambda req, timeout: FakeResponse(valid_payload()))
    result = normalize_resources(client.get_json("resources"), source="Verified source")

    assert len(result) == 1
    assert result[0]["name"] == "Support Centre"
    assert result[0]["category"] == "Education"
    assert result[0]["source_type"] == "api"
    assert result[0]["is_live"] is True
    assert result[0]["source"] == "Verified source"


def test_successful_response_with_list_payload():
    """Top-level list (not wrapped in ``data``) is also accepted."""
    payload = b'[{"name": "Legal Aid", "category": "Legal Support"}]'
    client = make_client(lambda req, timeout: FakeResponse(payload))
    result = normalize_resources(client.get_json("resources"), source="Test source")

    assert result[0]["name"] == "Legal Aid"
    assert result[0]["is_live"] is True


def test_empty_data_list_returns_empty_result():
    payload = b'{"data": []}'
    client = make_client(lambda req, timeout: FakeResponse(payload))
    result = normalize_resources(client.get_json("resources"), source="Test source")

    assert result == []


# ── Transport failures ────────────────────────────────────────────────────────

def test_timeout_raises_timeout_error():
    def raise_timeout(req, timeout):
        raise TimeoutError()

    with pytest.raises(ExternalAPIError) as exc_info:
        make_client(raise_timeout).get_json("resources")

    assert exc_info.value.code == "TIMEOUT"
    assert "did not respond" in exc_info.value.public_message


def test_connection_error_raises_connection_error():
    def raise_url_error(req, timeout):
        raise URLError("private connection details must not leak")

    with pytest.raises(ExternalAPIError) as exc_info:
        make_client(raise_url_error).get_json("resources")

    assert exc_info.value.code == "CONNECTION_ERROR"
    assert "could not be reached" in exc_info.value.public_message
    assert "private" not in exc_info.value.public_message


# ── HTTP errors ───────────────────────────────────────────────────────────────

def test_4xx_raises_client_error():
    def raise_404(req, timeout):
        raise make_http_error(404)

    with pytest.raises(ExternalAPIError) as exc_info:
        make_client(raise_404).get_json("resources")

    assert exc_info.value.code == "CLIENT_ERROR"
    assert "rejected" in exc_info.value.public_message


def test_401_raises_client_error():
    def raise_401(req, timeout):
        raise make_http_error(401)

    with pytest.raises(ExternalAPIError) as exc_info:
        make_client(raise_401).get_json("resources")

    assert exc_info.value.code == "CLIENT_ERROR"


def test_5xx_raises_server_error():
    def raise_503(req, timeout):
        raise make_http_error(503)

    with pytest.raises(ExternalAPIError) as exc_info:
        make_client(raise_503).get_json("resources")

    assert exc_info.value.code == "SERVER_ERROR"
    assert "temporarily unavailable" in exc_info.value.public_message


def test_500_raises_server_error():
    def raise_500(req, timeout):
        raise make_http_error(500)

    with pytest.raises(ExternalAPIError) as exc_info:
        make_client(raise_500).get_json("resources")

    assert exc_info.value.code == "SERVER_ERROR"


# ── Malformed response ────────────────────────────────────────────────────────

def test_malformed_json_raises_invalid_json():
    client = make_client(lambda req, timeout: FakeResponse(b"not-json{{"))

    with pytest.raises(ExternalAPIError) as exc_info:
        client.get_json("resources")

    assert exc_info.value.code == "INVALID_JSON"
    assert "invalid data" in exc_info.value.public_message


def test_bare_string_payload_raises_invalid_format():
    """A top-level JSON string is valid JSON but an invalid response shape."""
    client = make_client(lambda req, timeout: FakeResponse(b'"just a string"'))
    payload = client.get_json("resources")  # get_json succeeds — returns str

    with pytest.raises(ExternalAPIError) as exc_info:
        normalize_resources(payload, source="Test source")

    assert exc_info.value.code == "INVALID_FORMAT"


def test_bare_integer_payload_raises_invalid_format():
    client = make_client(lambda req, timeout: FakeResponse(b"42"))
    payload = client.get_json("resources")

    with pytest.raises(ExternalAPIError) as exc_info:
        normalize_resources(payload, source="Test source")

    assert exc_info.value.code == "INVALID_FORMAT"


def test_mapping_without_data_key_containing_non_list_raises_invalid_format():
    """A dict whose ``data`` value is not a list should be rejected."""
    payload = {"data": "not a list"}

    with pytest.raises(ExternalAPIError) as exc_info:
        normalize_resources(payload, source="Test source")

    assert exc_info.value.code == "INVALID_FORMAT"


# ── Missing required fields ───────────────────────────────────────────────────

def test_missing_name_raises_missing_fields():
    with pytest.raises(ExternalAPIError) as exc_info:
        normalize_resources(
            {"data": [{"category": "Healthcare", "description": "A clinic"}]},
            source="Test source",
        )

    assert exc_info.value.code == "MISSING_FIELDS"
    assert "incomplete record" in exc_info.value.public_message


def test_missing_category_raises_missing_fields():
    with pytest.raises(ExternalAPIError) as exc_info:
        normalize_resources(
            {"data": [{"name": "City Clinic"}]},
            source="Test source",
        )

    assert exc_info.value.code == "MISSING_FIELDS"


def test_empty_name_raises_missing_fields():
    """A name that is present but blank should be treated as missing."""
    with pytest.raises(ExternalAPIError) as exc_info:
        normalize_resources(
            {"data": [{"name": "  ", "category": "Healthcare"}]},
            source="Test source",
        )

    assert exc_info.value.code == "MISSING_FIELDS"


def test_optional_fields_default_to_empty_string():
    """Records without optional fields should normalize without error."""
    result = normalize_resources(
        {"data": [{"name": "Basic Centre", "category": "Shelter"}]},
        source="Test source",
    )

    assert result[0]["description"] == ""
    assert result[0]["location"] == ""
    assert result[0]["contact"] == ""
    assert result[0]["url"] == ""
    assert result[0]["language"] == ""
    assert result[0]["last_updated"] == ""


# ── Fallback behavior ─────────────────────────────────────────────────────────

def test_timeout_uses_non_live_database_fallback():
    def raise_timeout(req, timeout):
        raise TimeoutError()

    result = fetch_with_fallback(
        make_client(raise_timeout),
        "resources",
        source="Verified source",
        fallback_loader=lambda: [{"name": "Stored Centre", "category": "Education"}],
    )

    assert len(result) == 1
    assert result[0]["name"] == "Stored Centre"
    assert result[0]["source_type"] == "database"
    assert result[0]["is_live"] is False
    assert result[0]["source"] == "PostgreSQL verified data"


def test_connection_error_uses_database_fallback():
    def raise_url_error(req, timeout):
        raise URLError("no network")

    result = fetch_with_fallback(
        make_client(raise_url_error),
        "resources",
        source="Verified source",
        fallback_loader=lambda: [{"name": "Cached Resource", "category": "Legal Support"}],
    )

    assert result[0]["is_live"] is False
    assert result[0]["source_type"] == "database"


def test_5xx_error_uses_database_fallback():
    def raise_500(req, timeout):
        raise make_http_error(500)

    result = fetch_with_fallback(
        make_client(raise_500),
        "resources",
        source="Verified source",
        fallback_loader=lambda: [{"name": "Fallback Resource", "category": "Healthcare"}],
    )

    assert result[0]["is_live"] is False
    assert result[0]["name"] == "Fallback Resource"


def test_live_path_success_does_not_call_fallback():
    fallback_called = []

    def record_fallback():
        fallback_called.append(True)
        return []

    client = make_client(lambda req, timeout: FakeResponse(valid_payload()))
    result = fetch_with_fallback(
        client,
        "resources",
        source="Verified source",
        fallback_loader=record_fallback,
    )

    assert fallback_called == [], "fallback must not be called when live fetch succeeds"
    assert result[0]["is_live"] is True


# ── NormalizedResource unit tests ─────────────────────────────────────────────

def test_normalized_resource_as_dict_round_trip():
    resource = NormalizedResource(
        name="Pune Legal Aid",
        category="Legal Support",
        description="Free advice",
        location="Shivajinagar, Pune",
        contact="+91-20-12345678",
        url="https://example.org",
        language="en",
        source="Test source",
        source_type="official_data",
        last_updated="2026-09-01",
        is_live=True,
    )
    data = resource.as_dict()

    assert data["name"] == "Pune Legal Aid"
    assert data["source_type"] == "official_data"
    assert data["is_live"] is True
    assert data["last_updated"] == "2026-09-01"


def test_normalize_resource_invalid_source_type_raises_value_error():
    with pytest.raises(ValueError, match="source_type must be"):
        normalize_resource(
            {"name": "Test", "category": "General"},
            source="Test source",
            source_type="unknown_type",
        )


def test_normalize_resource_database_source_type_is_not_live():
    result = normalize_resource(
        {"name": "DB Resource", "category": "Healthcare"},
        source="PostgreSQL verified data",
        source_type="database",
        is_live=False,
    )

    assert result.source_type == "database"
    assert result.is_live is False
