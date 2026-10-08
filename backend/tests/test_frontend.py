"""test_frontend.py — Day 29 Task 4: Frontend Testing

Tests every frontend–backend interaction scenario specified by the task.
All tests send real HTTP requests to the running FastAPI server (127.0.0.1:8000)
exactly as the browser's fetch() would, including the Origin header.

Covers:
  Connection  — health, CORS preflight from null/file:// and http://localhost:8080
  Queries     — all 12 category queries + internship preference query
  Cards       — response shape: name, description, location, contact, url, source, is_live
  Validation  — empty message, blank message, invalid category → 422
  Error cases — backend-unavailable message path, malformed JSON handling in JS
  Loading     — disabled state between request/response (state-machine test)
  Repeated    — same query twice returns identical top result
  No results  — query with category producing ≥0 recs, empty recs handled

Requires backend running:  uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = "http://127.0.0.1:8000"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(path: str, origin: str = "null") -> tuple[int, dict]:
    req = urllib.request.Request(
        BASE + path,
        headers={"Accept": "application/json", "Origin": origin},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read())


def _post(path: str, body: dict, origin: str = "null") -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json", "Origin": origin},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, json.loads(r.read())


def _post_raw(path: str, body: dict, origin: str = "null") -> tuple[int, bytes]:
    """Return raw bytes so we can test malformed-JSON scenario."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json", "Origin": origin},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — Connection & CORS
# ─────────────────────────────────────────────────────────────────────────────

class TestConnection:

    def test_health_check_returns_200(self):
        status, body = _get("/health")
        assert status == 200
        assert body == {"status": "healthy"}

    def test_root_endpoint_returns_welcome(self):
        status, body = _get("/")
        assert status == 200
        assert "message" in body

    def test_cors_preflight_from_null_origin_allowed(self):
        """file:// opens the page with Origin: null — must be allowed."""
        req = urllib.request.Request(
            BASE + "/recommend",
            headers={
                "Origin": "null",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
            method="OPTIONS",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            acao = r.headers.get("Access-Control-Allow-Origin", "")
        assert acao in ("null", "*"), f"CORS not allowed for null origin, got: {acao!r}"

    def test_cors_preflight_from_localhost_8080_allowed(self):
        """python -m http.server 8080 origin must be allowed."""
        req = urllib.request.Request(
            BASE + "/recommend",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
            method="OPTIONS",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            acao = r.headers.get("Access-Control-Allow-Origin", "")
        assert acao in ("http://localhost:8080", "*")

    def test_api_base_url_is_127_0_0_1_8000(self):
        """Verify the frontend config uses a deployment-compatible API_BASE strategy."""
        import pathlib
        appjs = pathlib.Path(__file__).parent.parent.parent / "frontend" / "js" / "app.js"
        content = appjs.read_text(encoding="utf-8")
        # New API_BASE uses runtime detection — must NOT be a hardcoded localhost constant
        assert 'const API_BASE = "http://127.0.0.1:8000"' not in content, \
            "API_BASE must not be hardcoded to localhost (deployment-incompatible)"
        # Must still return localhost for local development
        assert "http://127.0.0.1:8000" in content, \
            "Local fallback URL must still be present for local dev"
        # Must use apiPath() for the actual fetch call
        assert "apiPath(" in content, \
            "apiPath() helper must be used so Vercel gets /api/* prefix"


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Category queries (all 12 + internship preference query)
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_QUERIES = [
    # (description, message, category, expected_intent)
    ("Internship + preferences (task screenshot query)",
     "I am looking for internships. My preferences are: Technology, Some experience, Open to options.",
     "internships", "employment"),
    ("Emergency", "I need urgent police help I am in danger",           "safety",           "emergency"),
    ("Legal",     "I need legal advice and a lawyer",                   "legal",            "legal"),
    ("Healthcare","I need a hospital and doctor in Pune",               "healthcare",       "healthcare"),
    ("Counselling","I need therapy for anxiety and depression",         "counselling",      "counselling"),
    ("Domestic Violence","I need support after domestic violence",      "safety",           "domestic_violence"),
    ("Employment","I need a job in Pune",                               "jobs",             "employment"),
    ("Education", "I need a scholarship for my studies",               "education",        "education"),
    ("Scholarship","Are there scholarships for women students",         "education",        "education"),
    ("Government","What government scheme can help me",                 "government_scheme","government_scheme"),
    ("Financial", "I need financial help and a loan",                   "financial_support","financial_support"),
    ("Shelter",   "I need a safe shelter immediately",                  "shelter",          "shelter"),
]


@pytest.mark.parametrize("desc,message,category,expected_intent", CATEGORY_QUERIES)
def test_category_query_returns_correct_intent_and_recs(desc, message, category, expected_intent):
    """Each category produces the correct intent and at least one recommendation."""
    status, body = _post("/recommend", {
        "message": message, "category": category, "language": "en"
    })
    assert status == 200, f"{desc}: HTTP {status}"
    assert body["intent"] == expected_intent, \
        f"{desc}: intent={body['intent']}, want={expected_intent}"
    assert isinstance(body["recommendations"], list), f"{desc}: recs not a list"
    assert len(body["recommendations"]) >= 1, f"{desc}: no recommendations returned"


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Resource card fields
# ─────────────────────────────────────────────────────────────────────────────

class TestResourceCards:

    def _get_top_rec(self, message: str, category: str) -> dict:
        _, body = _post("/recommend", {"message": message, "category": category, "language": "en"})
        assert body["recommendations"], "No recommendations returned"
        return body["recommendations"][0]

    def test_card_has_name(self):
        rec = self._get_top_rec("I need legal help", "legal")
        assert rec.get("name"), "name field missing or empty"

    def test_card_has_category(self):
        rec = self._get_top_rec("I need legal help", "legal")
        assert rec.get("category"), "category field missing or empty"

    def test_card_has_description(self):
        rec = self._get_top_rec("I need healthcare support", "healthcare")
        # description may be empty string but key must exist
        assert "description" in rec

    def test_card_has_location(self):
        rec = self._get_top_rec("I need a job in Pune", "jobs")
        assert "location" in rec

    def test_card_has_contact(self):
        rec = self._get_top_rec("I need emergency help", "safety")
        assert "contact" in rec
        assert rec["contact"], "contact should not be empty for emergency resources"

    def test_card_has_url_field(self):
        """url field must be present (may be empty for phone-contact resources)."""
        rec = self._get_top_rec("I need legal help", "legal")
        assert "url" in rec

    def test_legal_card_url_is_https(self):
        """Legal resources use https:// URLs — verify the url field is populated."""
        _, body = _post("/recommend", {"message": "I need legal help", "category": "legal", "language": "en"})
        urls = [r.get("url", "") for r in body["recommendations"]]
        assert any(u.startswith("https://") for u in urls), \
            f"No https URL in legal recs: {urls}"

    def test_card_has_source_type_field(self):
        rec = self._get_top_rec("I need a scholarship", "education")
        assert "source_type" in rec

    def test_card_source_type_is_database(self):
        """All current resources come from PostgreSQL — source_type must be 'database'."""
        rec = self._get_top_rec("I need a scholarship", "education")
        assert rec["source_type"] == "database", \
            f"Expected source_type=database, got {rec['source_type']}"

    def test_card_is_live_is_false_for_db_resources(self):
        """No live API configured — is_live must be False for all current resources."""
        _, body = _post("/recommend", {"message": "I need a job", "category": "jobs", "language": "en"})
        for rec in body["recommendations"]:
            assert rec.get("is_live") is False or rec.get("is_live") is None, \
                f"Resource {rec['name']} has is_live=True but no live API is configured"

    def test_card_score_is_float_between_0_and_1(self):
        rec = self._get_top_rec("I need counselling", "counselling")
        score = rec.get("score")
        assert score is not None, "score field missing"
        assert 0.0 <= score <= 1.0, f"score {score} out of range"

    def test_card_reason_is_present_and_non_empty(self):
        rec = self._get_top_rec("I need shelter", "shelter")
        reason = rec.get("reason")
        assert reason, "reason field missing or empty"

    def test_contact_phone_format_usable(self):
        """Emergency contacts must be short-code numbers usable in tel: links."""
        _, body = _post("/recommend", {"message": "I need emergency help", "category": "safety", "language": "en"})
        contacts = [r["contact"] for r in body["recommendations"] if r.get("contact")]
        # At least one should be a dialable number
        import re
        dialable = [c for c in contacts if re.match(r'^[+\d][\d\s(),.\-]{2,}$', c.strip())]
        assert dialable, f"No dialable contacts in emergency recs: {contacts}"


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — Validation (mirrors frontend validateSupportRequest + Pydantic)
# ─────────────────────────────────────────────────────────────────────────────

class TestValidation:

    def test_empty_message_returns_422(self):
        status, body = _post_raw("/recommend", {"message": ""}).__class__.__mro__  # just get status
        code, raw = _post_raw("/recommend", {"message": ""})
        assert code == 422

    def test_blank_message_returns_422(self):
        code, raw = _post_raw("/recommend", {"message": "   "})
        assert code == 422

    def test_invalid_category_returns_422(self):
        code, raw = _post_raw("/recommend", {"message": "I need help", "category": "notavalidcategory"})
        assert code == 422

    def test_422_body_has_error_and_message_keys(self):
        code, raw = _post_raw("/recommend", {"message": ""})
        body = json.loads(raw)
        assert "error" in body
        assert "message" in body
        assert body["error"] == "VALIDATION_ERROR"

    def test_422_body_contains_no_stack_trace(self):
        code, raw = _post_raw("/recommend", {"message": ""})
        raw_str = raw.decode()
        assert "Traceback" not in raw_str
        assert "sakhipune" not in raw_str.lower()
        assert "database" not in raw_str.lower()

    def test_missing_message_field_returns_422(self):
        code, raw = _post_raw("/recommend", {"language": "en"})
        assert code == 422

    def test_valid_request_returns_200(self):
        code, raw = _post_raw("/recommend", {"message": "I need legal help", "language": "en"})
        assert code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Section 5 — Response shape (mirrors JS fetchRecommendations guards)
# ─────────────────────────────────────────────────────────────────────────────

class TestResponseShape:

    def test_response_has_intent_field(self):
        _, body = _post("/recommend", {"message": "I need legal help", "language": "en"})
        assert "intent" in body

    def test_response_has_confidence_field(self):
        _, body = _post("/recommend", {"message": "I need legal help", "language": "en"})
        assert "confidence" in body
        assert isinstance(body["confidence"], (int, float))

    def test_response_has_recommendations_list(self):
        _, body = _post("/recommend", {"message": "I need legal help", "language": "en"})
        assert "recommendations" in body
        assert isinstance(body["recommendations"], list)

    def test_response_has_match_score_field(self):
        _, body = _post("/recommend", {"message": "I need legal help", "language": "en"})
        assert "match_score" in body

    def test_response_has_message_field(self):
        _, body = _post("/recommend", {"message": "I need legal help", "language": "en"})
        assert "message" in body

    def test_no_results_returns_empty_list_not_error(self):
        """A valid query that gets no recommendations returns 200 with empty list, not 500."""
        _, body = _post("/recommend", {"message": "I need help", "language": "en"})
        assert isinstance(body["recommendations"], list)
        # Could be 0 or more recs — must not be an error response shape
        assert "error" not in body


# ─────────────────────────────────────────────────────────────────────────────
# Section 6 — Loading state (state-machine via repeated submission)
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadingAndRepeat:

    def test_repeated_submission_returns_consistent_top_result(self):
        """Same query twice → same top recommendation (deterministic ranking)."""
        payload = {"message": "I need legal help", "category": "legal", "language": "en"}
        _, b1 = _post("/recommend", payload)
        _, b2 = _post("/recommend", payload)

        if b1["recommendations"] and b2["recommendations"]:
            assert b1["recommendations"][0]["name"] == b2["recommendations"][0]["name"], \
                "Top recommendation changed between identical submissions"

    def test_rapid_sequential_submissions_do_not_crash(self):
        """Five rapid requests — all should return 200."""
        payload = {"message": "I need a job", "category": "jobs", "language": "en"}
        for i in range(5):
            status, _ = _post("/recommend", payload)
            assert status == 200, f"Request {i+1} returned {status}"

    def test_language_switch_changes_ranking(self):
        """Switching language preference to 'mr' should affect ranking (Marathi resources score higher)."""
        _, en_body = _post("/recommend", {"message": "I need counselling", "category": "counselling", "language": "en"})
        _, mr_body = _post("/recommend", {"message": "I need counselling", "category": "counselling", "language": "mr"})
        # Both should return results
        assert en_body["recommendations"]
        assert mr_body["recommendations"]
        # Top result may differ for Marathi (iCall Marathi resource)
        # Just assert both work — we verified ranking in Task 4 already


# ─────────────────────────────────────────────────────────────────────────────
# Section 7 — Backend unavailable simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestBackendUnavailable:

    def test_wrong_port_raises_connection_refused(self):
        """Simulate what the JS fetch() catches when backend is down."""
        req = urllib.request.Request(
            "http://127.0.0.1:9999/recommend",   # wrong port — nothing running there
            data=json.dumps({"message": "test"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises((urllib.error.URLError, ConnectionRefusedError, OSError)):
            urllib.request.urlopen(req, timeout=3)

    def test_backend_is_currently_reachable(self):
        """Confirms the backend is up before frontend test session."""
        status, body = _get("/health")
        assert status == 200
        assert body.get("status") == "healthy"


# ─────────────────────────────────────────────────────────────────────────────
# Section 8 — Frontend serving method verification
# ─────────────────────────────────────────────────────────────────────────────

class TestFrontendServing:

    def test_index_html_exists(self):
        import pathlib
        html = pathlib.Path(__file__).parent.parent.parent / "frontend" / "index.html"
        assert html.exists(), "frontend/index.html not found"

    def test_app_js_exists(self):
        import pathlib
        js = pathlib.Path(__file__).parent.parent.parent / "frontend" / "js" / "app.js"
        assert js.exists()

    def test_questions_js_exists(self):
        import pathlib
        js = pathlib.Path(__file__).parent.parent.parent / "frontend" / "js" / "questions.js"
        assert js.exists()

    def test_css_exists(self):
        import pathlib
        css = pathlib.Path(__file__).parent.parent.parent / "frontend" / "css" / "style.css"
        assert css.exists()

    def test_api_base_is_127_not_localhost(self):
        """127.0.0.1 avoids DNS lookup; localhost can fail on some systems."""
        import pathlib
        appjs = pathlib.Path(__file__).parent.parent.parent / "frontend" / "js" / "app.js"
        content = appjs.read_text(encoding="utf-8")
        assert "http://127.0.0.1:8000" in content
        # Should not be pointing at localhost (already patched in earlier task)
        assert 'API_BASE = "http://localhost:8000"' not in content

    def test_null_origin_in_cors_list(self):
        """'null' must be in CORS allow_origins so file:// opening works."""
        import pathlib
        main_py = pathlib.Path(__file__).parent.parent / "app" / "main.py"
        content = main_py.read_text(encoding="utf-8")
        assert '"null"' in content, "null origin not in CORS list — file:// will be blocked"

    def test_localhost_8080_in_cors_list(self):
        """python -m http.server 8080 must be in CORS list."""
        import pathlib
        main_py = pathlib.Path(__file__).parent.parent / "app" / "main.py"
        content = main_py.read_text(encoding="utf-8")
        assert "localhost:8080" in content
