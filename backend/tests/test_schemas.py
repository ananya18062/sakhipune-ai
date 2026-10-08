import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.schemas import SupportRequest, UserQuery


class TestSupportRequest:

    def test_accepts_structured_request(self):
        request = SupportRequest(
            message="I want an internship in AI",
            category="internship",
            preferences={"field": "AI/ML", "experience": "fresher"},
            language="English",
        )

        assert request.message == "I want an internship in AI"
        assert request.category == "internships"
        assert request.preferences["field"] == "AI/ML"
        assert request.language == "en"

    def test_optional_fields_default_to_none(self):
        request = SupportRequest(message="I need support")

        assert request.category is None
        assert request.preferences is None
        assert request.language is None

    def test_strips_message_whitespace(self):
        request = SupportRequest(message="  I need legal help  ")

        assert request.message == "I need legal help"

    def test_normalizes_supported_language(self):
        assert SupportRequest(message="I need support", language="Marathi").language == "mr"

    def test_rejects_unsupported_language(self):
        with pytest.raises(ValidationError, match="language must be English, Hindi, or Marathi"):
            SupportRequest(message="I need support", language="French")

    def test_rejects_blank_message(self):
        with pytest.raises(ValidationError, match="message must not be empty or blank"):
            SupportRequest(message="   ")

    def test_rejects_unknown_category(self):
        with pytest.raises(ValidationError, match="category must be a supported SakhiPune category"):
            SupportRequest(message="I need support", category="unknown")

    def test_rejects_blank_category(self):
        with pytest.raises(ValidationError, match="category must be a supported SakhiPune category"):
            SupportRequest(message="I need support", category="  ")


class TestExistingUserQuery:

    def test_existing_schema_still_accepts_message_and_language(self):
        query = UserQuery(message="I need a job", language="en")

        assert query.message == "I need a job"
        assert query.language == "en"