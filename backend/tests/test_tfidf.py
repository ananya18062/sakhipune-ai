import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.tfidf_service import (
    build_resource_text,
    fit_tfidf,
    transform_query,
)


class TestBuildResourceText:

    def test_builds_text_from_resource_fields(self):
        resource = {
            "name": "Pune Women Skill Centre",
            "category": "Employment",
            "description": "Career and job training support.",
            "keywords": "job, career, skill",
            "location": "Pune",
            "contact": "not-for-vector-search@example.org",
        }

        result = build_resource_text(resource)

        assert result == (
            "Pune Women Skill Centre Employment "
            "Career and job training support. job, career, skill"
        )
        assert "Pune" not in result.split()[-1:]
        assert "not-for-vector-search@example.org" not in result

    def test_supports_resource_objects(self):
        resource = SimpleNamespace(
            name="Legal Aid",
            category="Legal",
            description="Rights guidance",
            keywords="law, advice",
        )

        assert build_resource_text(resource) == "Legal Aid Legal Rights guidance law, advice"

    def test_empty_resource_returns_empty_text(self):
        assert build_resource_text({}) == ""


class TestTfidfRepresentation:

    def test_empty_documents_are_rejected(self):
        with pytest.raises(ValueError, match="at least one non-empty resource document"):
            fit_tfidf([])

    def test_fit_generates_resource_matrix(self):
        vectorizer, matrix = fit_tfidf([
            "employment job career support",
            "legal rights advice support",
        ])

        assert matrix.shape[0] == 2
        assert matrix.shape[1] == len(vectorizer.get_feature_names_out())
        assert matrix.nnz > 0

    def test_transform_query_generates_matching_vector(self):
        vectorizer, resource_matrix = fit_tfidf([
            "employment job career support",
            "legal rights advice support",
        ])

        query_vector = transform_query(vectorizer, "I need a job")

        assert query_vector.shape == (1, resource_matrix.shape[1])
        assert query_vector.nnz > 0

    def test_empty_query_returns_zero_vector(self):
        vectorizer, resource_matrix = fit_tfidf(["job support"])

        query_vector = transform_query(vectorizer, "   ")

        assert query_vector.shape == (1, resource_matrix.shape[1])
        assert query_vector.nnz == 0
