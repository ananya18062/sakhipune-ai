import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.tfidf_service import (
    calculate_similarity,
    fit_tfidf,
    transform_query,
)


def test_related_resource_scores_higher_than_unrelated_resource():
    resource_texts = [
        "Scholarship and education financial support",
        "Job placement and employment support",
    ]
    vectorizer, resource_vectors = fit_tfidf(resource_texts)
    query_vector = transform_query(vectorizer, "I need a scholarship")

    scholarship_score = calculate_similarity(query_vector, resource_vectors[0])
    employment_score = calculate_similarity(query_vector, resource_vectors[1])

    assert 0.0 <= scholarship_score <= 1.0
    assert 0.0 <= employment_score <= 1.0
    assert scholarship_score > employment_score


def test_identical_text_has_maximum_similarity():
    vectorizer, resource_vectors = fit_tfidf(["legal advice and rights"])
    query_vector = transform_query(vectorizer, "legal advice and rights")

    assert calculate_similarity(query_vector, resource_vectors[0]) == 1.0


def test_unrelated_text_has_zero_similarity():
    vectorizer, resource_vectors = fit_tfidf(["job placement support"])
    query_vector = transform_query(vectorizer, "scholarship education")

    assert calculate_similarity(query_vector, resource_vectors[0]) == 0.0


def test_empty_query_vector_has_zero_similarity():
    vectorizer, resource_vectors = fit_tfidf(["job placement support"])
    query_vector = transform_query(vectorizer, "")

    assert calculate_similarity(query_vector, resource_vectors[0]) == 0.0