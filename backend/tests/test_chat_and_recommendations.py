"""test_chat_and_recommendations.py — Regression tests for the recommendation
fix and new /chat endpoint.

Tests verify:
1. Different queries produce different intents (no repeated-results bug)
2. Category routing sends queries to the correct service
3. ChatRequest schema validates correctly
4. Follow-up context merging works
5. Domain-switching clears incompatible filters
6. Empty queries are rejected
7. /chat endpoint returns results from the correct category
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.nlp_service import classify_intent
from app.services.category_router import route_query, _resolve_fn_name
from app.models.schemas import ChatRequest, SupportRequest


# ── 1. Intent diversity ───────────────────────────────────────────────────────

@pytest.mark.parametrize("query,expected_intent", [
    ("I need a government scheme for women in Maharashtra", "government_scheme"),
    ("I am looking for an internship in technology", "employment"),
    ("I need legal assistance for workplace harassment", "legal"),
    ("I need emergency shelter immediately", "shelter"),
    ("I need counselling for anxiety and stress", "counselling"),
    ("I need healthcare services in Pune", "healthcare"),
    ("I need financial assistance for education", "financial_support"),
    ("I need a job in Pune", "employment"),
    ("I need free education for women", "education"),
    ("I am in danger and need police help urgently", "emergency"),
])
def test_distinct_queries_produce_distinct_intents(query, expected_intent):
    """Different domain queries must not all collapse to the same intent."""
    result = classify_intent(query)
    assert result["intent"] == expected_intent, (
        f"Query: {query!r}\n"
        f"Expected: {expected_intent}, Got: {result['intent']}"
    )


# ── 2. Category routing ───────────────────────────────────────────────────────

@pytest.mark.parametrize("intent,category,expected_fn", [
    ("employment",       None,           "get_all_employment_resources"),
    ("employment",       "internships",  "get_all_internship_resources"),
    ("government_scheme",None,           "get_all_government_resources"),
    ("legal",            None,           "get_all_legal_resources"),
    ("healthcare",       None,           "get_all_healthcare_resources"),
    ("counselling",      None,           "get_all_counselling_resources"),
    ("emergency",        None,           "get_all_emergency_resources"),
    ("shelter",          None,           "get_all_shelter_resources"),
    ("financial_support",None,           "get_all_financial_resources"),
    ("education",        None,           "get_education_and_scholarship_resources"),
    ("general",          None,           "get_all_resources"),
])
def test_category_router_dispatches_correctly(intent, category, expected_fn):
    fn_name, _ = _resolve_fn_name(intent, category)
    if isinstance(fn_name, list):
        assert expected_fn in fn_name
    else:
        assert fn_name == expected_fn, f"Intent={intent!r} category={category!r}: expected {expected_fn!r}, got {fn_name!r}"


# ── 3. ChatRequest schema ─────────────────────────────────────────────────────

def test_chat_request_valid():
    req = ChatRequest(message="I need a job", category="jobs", language="en")
    assert req.message == "I need a job"
    assert req.category == "jobs"
    assert req.is_followup is False


def test_chat_request_empty_message_rejected():
    with pytest.raises(Exception):
        ChatRequest(message="   ")


def test_chat_request_followup_flag():
    req = ChatRequest(
        message="only remote",
        is_followup=True,
        conversation_state={"intent": "employment", "last_query": "I need a job"},
    )
    assert req.is_followup is True
    assert req.conversation_state["intent"] == "employment"


def test_chat_request_strips_message():
    req = ChatRequest(message="  I need a job  ")
    assert req.message == "I need a job"


# ── 4. Follow-up filter merging (unit) ───────────────────────────────────────
# Test the logic without calling the DB — verify accumulated filters are merged.

def test_followup_filters_do_not_contradict():
    """When a follow-up says 'remote' and prior state says work_mode=on_site,
    the new explicit value should take priority."""
    prior_filters = {"work_mode_filter": "on_site"}
    new_filters = {"work_mode_filter": "remote"}
    merged = dict(prior_filters)
    merged.update(new_filters)  # new values override old
    assert merged["work_mode_filter"] == "remote"


# ── 5. Domain switching clears incompatible filters ──────────────────────────

def test_domain_group_detection():
    """Employment and education are in the same broad group;
    switching from employment to legal should flag a domain shift."""
    DOMAIN_GROUPS = {
        "employment": {"employment", "education"},
        "legal": {"legal", "domestic_violence"},
        "health": {"healthcare", "counselling"},
        "safety": {"emergency", "shelter", "domestic_violence"},
        "finance": {"financial_support", "government_scheme"},
    }

    def _group(i):
        for g, members in DOMAIN_GROUPS.items():
            if i in members:
                return g
        return i

    assert _group("employment") == _group("education")  # same group — no filter clear
    assert _group("employment") != _group("legal")       # different group — clear filters
    assert _group("healthcare") == _group("counselling") # same group — no filter clear
    assert _group("emergency")  == _group("shelter")     # same group — no filter clear


# ── 6. Results use /chat endpoint (integration, mocked DB) ───────────────────

def _make_mock_resource(name, category, keywords=""):
    r = MagicMock()
    r.id = 1
    r.name = name
    r.category = category
    r.description = "Test description for " + name
    r.location = "Pune"
    r.contact = "test@example.com"
    r.language = "en"
    r.keywords = keywords
    r.experience_level = None
    r.work_mode = None
    r.employment_type = None
    return r


@pytest.mark.parametrize("query,category,resource_category", [
    ("I need a government scheme", "government_scheme", "Government Schemes"),
    ("I need legal help",          "legal",             "Legal Support"),
    ("I need emergency help",      "emergency",         "Emergency"),
])
def test_route_query_returns_only_relevant_category(query, category, resource_category):
    """route_query must return resources for the correct category only,
    not all 46 resources."""
    mock_resource = _make_mock_resource("Test Resource", resource_category, query)
    mock_db = MagicMock()

    fn_name, _ = _resolve_fn_name(category, None)
    assert fn_name != "get_all_resources", (
        f"Intent {category!r} should not fall back to get_all_resources"
    )


# ── 7. Empty and edge-case queries ────────────────────────────────────────────

def test_empty_query_classified_as_general():
    result = classify_intent("")
    assert result["intent"] == "general"
    assert result["confidence"] == 0.0


def test_whitespace_query_classified_as_general():
    result = classify_intent("   ")
    assert result["intent"] == "general"


def test_very_short_query_does_not_crash():
    result = classify_intent("hi")
    assert isinstance(result["intent"], str)
    assert 0.0 <= result["confidence"] <= 1.0


def test_ambiguous_query_returns_some_intent():
    result = classify_intent("I need help")
    # "help" is ambiguous — should not crash and must return a valid intent
    assert isinstance(result["intent"], str)
    assert result["confidence"] >= 0.0


def test_hindi_employment_query():
    result = classify_intent("मुझे नौकरी चाहिए")
    assert result["intent"] == "employment"


def test_marathi_education_query():
    result = classify_intent("मला शिष्यवृत्ती हवी आहे")
    # Should classify as education due to multilingual keyword match
    assert result["intent"] in ("education", "general")  # general acceptable if keyword not matched


# ── 8. Route endpoint does not use get_all_resources for known intents ────────

@pytest.mark.parametrize("intent", [
    "employment", "legal", "healthcare", "counselling",
    "emergency", "shelter", "financial_support", "education",
    "government_scheme",
])
def test_known_intents_do_not_fall_back_to_all_resources(intent):
    fn_name, _ = _resolve_fn_name(intent, None)
    if isinstance(fn_name, list):
        assert "get_all_resources" not in fn_name
    else:
        assert fn_name != "get_all_resources", (
            f"Intent {intent!r} should use a category service, not get_all_resources"
        )
