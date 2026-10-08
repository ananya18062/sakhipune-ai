"""test_resource_normalizer.py — Tests for the shared resource normalization layer.

Coverage:
  1.  orm_to_normalized: all 11 canonical fields present
  2.  orm_to_normalized: https contact is promoted to url
  3.  orm_to_normalized: phone contact is NOT promoted to url
  4.  orm_to_normalized: short emergency code (e.g. 100) not promoted
  5.  orm_to_normalized: language defaults to "en" when None
  6.  orm_to_normalized: keywords internal field is preserved
  7.  orm_to_normalized: None description/location handled gracefully
  8.  orm_to_normalized: source_type=database, is_live=False
  9.  orm_to_normalized: source can be overridden
  10. orm_to_normalized: malformed ORM object → empty dict, no crash

  11. normalize_from_dict: valid payload → correct output
  12. normalize_from_dict: missing name → ExternalAPIError MISSING_FIELDS
  13. normalize_from_dict: missing category → ExternalAPIError MISSING_FIELDS
  14. normalize_from_dict: empty name (blank string) → ExternalAPIError
  15. normalize_from_dict: extra unknown fields are ignored
  16. normalize_from_dict: is_live=True for API source
  17. normalize_from_dict: source_type=official_data accepted

  18. validate_normalized: valid dict passes without error
  19. validate_normalized: missing key raises ValueError
  20. validate_normalized: empty name raises ValueError
  21. validate_normalized: empty category raises ValueError
  22. validate_normalized: invalid source_type raises ValueError
  23. validate_normalized: non-dict input raises ValueError

  24. All 10 category services import _orm_to_normalized from resource_normalizer
  25. orm_to_normalized output is compatible with _dict_to_orm in routes.py
  26. keywords forwarded through _dict_to_orm to synthetic ORM object
  27. NORMALIZED_KEYS tuple contains all 11 expected keys
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.resource_normalizer import (
    NORMALIZED_KEYS,
    normalize_from_dict,
    orm_to_normalized,
    validate_normalized,
)
from app.services.api_clients.base_client import ExternalAPIError


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_orm(
    name="Sassoon General Hospital",
    category="Healthcare",
    description="Government hospital in Pune.",
    location="Agarkar Nagar, Pune 411001",
    contact="020-26128000",
    language="en",
    keywords="hospital,healthcare,women",
):
    r = MagicMock()
    r.id          = 42
    r.name        = name
    r.category    = category
    r.description = description
    r.location    = location
    r.contact     = contact
    r.language    = language
    r.keywords    = keywords
    return r


def _make_orm_url(contact="https://pmc.gov.in"):
    return _make_orm(contact=contact)


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — orm_to_normalized (tests 1–10)
# ─────────────────────────────────────────────────────────────────────────────

class TestOrmToNormalized:

    # 1. All 11 canonical fields present
    def test_all_canonical_fields_present(self):
        result = orm_to_normalized(_make_orm())
        for key in NORMALIZED_KEYS:
            assert key in result, f"Missing key: {key}"

    # 2. https contact promoted to url
    def test_https_contact_promoted_to_url(self):
        result = orm_to_normalized(_make_orm_url("https://pmc.gov.in"))
        assert result["url"] == "https://pmc.gov.in"
        assert result["contact"] == "https://pmc.gov.in"

    # 3. Phone contact NOT promoted to url
    def test_phone_contact_not_promoted_to_url(self):
        result = orm_to_normalized(_make_orm(contact="020-26128000"))
        assert result["url"] == ""
        assert result["contact"] == "020-26128000"

    # 4. Short emergency code not promoted
    def test_short_code_not_promoted_to_url(self):
        for code in ["100", "108", "181", "1091"]:
            result = orm_to_normalized(_make_orm(contact=code))
            assert result["url"] == "", f"Short code {code} should not become url"

    # 5. language defaults to "en" when None
    def test_language_defaults_to_en(self):
        result = orm_to_normalized(_make_orm(language=None))
        assert result["language"] == "en"

    # 6. keywords internal field is preserved
    def test_keywords_internal_field_preserved(self):
        result = orm_to_normalized(_make_orm(keywords="hospital,healthcare"))
        assert result["keywords"] == "hospital,healthcare"

    # 7. None description and location handled gracefully
    def test_none_description_location_handled(self):
        result = orm_to_normalized(_make_orm(description=None, location=None))
        assert result["description"] == ""
        assert result["location"] == ""

    # 8. Always marks as database, not live
    def test_marks_as_database_not_live(self):
        result = orm_to_normalized(_make_orm())
        assert result["source_type"] == "database"
        assert result["is_live"] is False
        assert result["source"] == "PostgreSQL verified data"

    # 9. Source can be overridden
    def test_source_can_be_overridden(self):
        result = orm_to_normalized(_make_orm(), source="Custom source")
        assert result["source"] == "Custom source"

    # 10. Malformed ORM (missing name) → empty dict, no crash
    def test_malformed_orm_returns_empty_dict(self):
        bad = MagicMock()
        bad.id = 0
        bad.name = ""          # empty name will fail normalize_resource
        bad.category = ""
        bad.description = ""
        bad.location = ""
        bad.contact = ""
        bad.language = "en"
        bad.keywords = ""
        result = orm_to_normalized(bad)
        assert result == {}    # graceful empty dict, no exception


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — normalize_from_dict (tests 11–17)
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeFromDict:

    # 11. Valid payload → all fields correct
    def test_valid_payload_normalizes_correctly(self):
        payload = {
            "name":        "Pune DLSA",
            "category":    "Legal Support",
            "description": "Free legal aid.",
            "location":    "Shivajinagar, Pune",
            "contact":     "https://punedlsa.org",
        }
        result = normalize_from_dict(payload, source="punedlsa.org", source_type="official_data")
        assert result["name"]        == "Pune DLSA"
        assert result["category"]    == "Legal Support"
        assert result["source"]      == "punedlsa.org"
        assert result["source_type"] == "official_data"
        assert result["is_live"]     is True

    # 12. Missing name → ExternalAPIError MISSING_FIELDS
    def test_missing_name_raises(self):
        with pytest.raises(ExternalAPIError, match="incomplete record"):
            normalize_from_dict(
                {"category": "Healthcare"},
                source="test",
            )

    # 13. Missing category → ExternalAPIError MISSING_FIELDS
    def test_missing_category_raises(self):
        with pytest.raises(ExternalAPIError, match="incomplete record"):
            normalize_from_dict(
                {"name": "Sassoon Hospital"},
                source="test",
            )

    # 14. Blank name treated as missing
    def test_blank_name_raises(self):
        with pytest.raises(ExternalAPIError, match="incomplete record"):
            normalize_from_dict(
                {"name": "   ", "category": "Healthcare"},
                source="test",
            )

    # 15. Extra unknown fields are silently ignored
    def test_extra_fields_are_ignored(self):
        result = normalize_from_dict(
            {
                "name": "Test Resource", "category": "Employment",
                "unknown_field": "ignored", "another_extra": 42,
            },
            source="test",
        )
        assert result["name"] == "Test Resource"
        assert "unknown_field" not in result

    # 16. is_live=True for API source (default)
    def test_is_live_true_for_api_source(self):
        result = normalize_from_dict(
            {"name": "Live Resource", "category": "Education"},
            source="test API",
            source_type="api",
            is_live=True,
        )
        assert result["is_live"] is True

    # 17. source_type=official_data is accepted
    def test_official_data_source_type_accepted(self):
        result = normalize_from_dict(
            {"name": "NHM", "category": "Healthcare"},
            source="nhm.gov.in",
            source_type="official_data",
        )
        assert result["source_type"] == "official_data"


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — validate_normalized (tests 18–23)
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateNormalized:

    def _valid(self):
        return {
            "name": "Test", "category": "Employment", "description": "",
            "location": "", "contact": "", "url": "", "language": "en",
            "source": "test", "source_type": "database",
            "last_updated": "", "is_live": False,
        }

    # 18. Valid dict passes without error
    def test_valid_dict_passes(self):
        validate_normalized(self._valid())  # should not raise

    # 19. Missing key raises ValueError
    def test_missing_key_raises(self):
        d = self._valid()
        del d["category"]
        with pytest.raises(ValueError, match="missing required key"):
            validate_normalized(d)

    # 20. Empty name raises ValueError
    def test_empty_name_raises(self):
        d = self._valid()
        d["name"] = "  "
        with pytest.raises(ValueError, match="empty 'name'"):
            validate_normalized(d)

    # 21. Empty category raises ValueError
    def test_empty_category_raises(self):
        d = self._valid()
        d["category"] = ""
        with pytest.raises(ValueError, match="empty 'category'"):
            validate_normalized(d)

    # 22. Invalid source_type raises ValueError
    def test_invalid_source_type_raises(self):
        d = self._valid()
        d["source_type"] = "live"
        with pytest.raises(ValueError, match="source_type"):
            validate_normalized(d)

    # 23. Non-dict input raises ValueError
    def test_non_dict_raises(self):
        with pytest.raises(ValueError, match="Expected a dict"):
            validate_normalized("not a dict")


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — Integration / compatibility (tests 24–27)
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizerIntegration:

    # 24. All 10 category services import from resource_normalizer
    def test_all_services_import_shared_normalizer(self):
        import importlib, pathlib
        services = [
            "education_service", "jobs_service", "internship_service",
            "healthcare_service", "legal_service", "financial_service",
            "shelter_service", "emergency_service", "counselling_service",
            "government_service",
        ]
        base = pathlib.Path(__file__).parent.parent / "app" / "services"
        for svc in services:
            txt = (base / f"{svc}.py").read_text(encoding="utf-8")
            assert "resource_normalizer" in txt, \
                f"{svc}.py does not import from resource_normalizer"
            assert "def _orm_to_normalized" not in txt, \
                f"{svc}.py still has a local _orm_to_normalized definition"

    # 25. orm_to_normalized output is compatible with _dict_to_orm in routes.py
    def test_normalized_dict_compatible_with_dict_to_orm(self):
        from app.api.routes import _dict_to_orm
        normalized = orm_to_normalized(_make_orm())
        orm_obj = _dict_to_orm(normalized)
        # Core fields must be preserved
        assert orm_obj.name        == normalized["name"]
        assert orm_obj.category    == normalized["category"]
        assert orm_obj.description == normalized["description"]
        assert orm_obj.location    == normalized["location"]
        assert orm_obj.contact     == normalized["contact"]
        assert orm_obj.language    == normalized["language"]

    # 26. keywords forwarded through _dict_to_orm to synthetic ORM object
    def test_keywords_forwarded_through_dict_to_orm(self):
        from app.api.routes import _dict_to_orm
        normalized = orm_to_normalized(_make_orm(keywords="hospital,healthcare,women"))
        orm_obj = _dict_to_orm(normalized)
        assert orm_obj.keywords == "hospital,healthcare,women"

    # 27. NORMALIZED_KEYS contains all 11 expected keys
    def test_normalized_keys_complete(self):
        expected = {
            "name", "category", "description", "location", "contact",
            "url", "language", "source", "source_type", "last_updated", "is_live",
        }
        assert set(NORMALIZED_KEYS) == expected
        assert len(NORMALIZED_KEYS) == 11
