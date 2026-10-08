import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.recommendation_service import (
    calculate_final_score,
    calculate_location_score,
    rank_resources,
    rank_resources_with_scores,
    run_recommendation_pipeline,
)


def resource(name, category, description, keywords):
    return SimpleNamespace(
        name=name,
        category=category,
        description=description,
        keywords=keywords,
    )


def test_hybrid_ranking_prefers_matching_category_and_text():
    resources = [
        resource("Scholarship Centre", "Education", "Scholarship and education financial support", "scholarship, education"),
        resource("Job Placement", "Employment", "Job placement and employment support", "job, employment"),
    ]

    ranked = rank_resources(
        "I need a scholarship",
        "education",
        resources,
        category="education",
    )

    assert ranked[0].name == "Scholarship Centre"
    assert len(ranked) == 2


def test_preferences_can_influence_relevant_results():
    resources = [
        resource("General Education Centre", "Education", "Education guidance", "education"),
        resource("STEM Scholarship Centre", "Education", "Scholarship for technology students", "scholarship, technology, AI"),
    ]

    ranked = rank_resources(
        "I need support",
        "education",
        resources,
        preferences={"field": "technology", "support": "scholarship"},
    )

    assert ranked[0].name == "STEM Scholarship Centre"


def test_field_preference_ranks_ai_resources_higher():
    resources = [
        resource("General Internship", "Employment", "Internship and career support", "internship"),
        resource("AI Learning Lab", "Employment", "AI machine learning and data science internship", "AI, ML, data science"),
    ]

    ranked = rank_resources(
        "I need support",
        "employment",
        resources,
        category="internships",
        preferences={"field": "AI/ML"},
        weights={"intent": 0.2, "similarity": 0.2, "category": 0.1, "preference": 0.5},
    )

    assert ranked[0].name == "AI Learning Lab"


def test_location_score_uses_coarse_pune_relevance():
    assert calculate_location_score("Shivajinagar, Pune", "Pune") == 1.0
    assert calculate_location_score("Pimpri-Chinchwad", "Pune") == 0.6
    assert calculate_location_score("Online", "Pune") == 0.4
    assert calculate_location_score("Nagpur", "Pune") == 0.0


def test_language_alias_matches_resource_language_code():
    resources = [
        resource("English Support", "Education", "Scholarship support", "scholarship"),
        resource("Marathi Support", "Education", "Scholarship support", "scholarship"),
    ]
    resources[0].language = "en"
    resources[1].language = "mr"

    ranked = rank_resources("I need a scholarship", "education", resources, language="Marathi")

    assert ranked[0].name == "Marathi Support"


def test_pune_resource_ranks_above_online_fallback():
    resources = [
        resource("Online Support", "Education", "Scholarship education support", "scholarship"),
        resource("Pune Support", "Education", "Scholarship education support", "scholarship"),
    ]
    resources[0].location = "Online"
    resources[1].location = "Pune"

    ranked = rank_resources("I need a scholarship", "education", resources)

    assert ranked[0].name == "Pune Support"


def test_experience_preference_is_used_for_current_session_only():
    resources = [
        resource("Fresher Programme", "Employment", "Entry-level employment support", "fresher beginner"),
        resource("Senior Careers", "Employment", "Experienced professional career support", "experienced senior"),
    ]

    ranked = rank_resources(
        "I need work",
        "employment",
        resources,
        preferences={"experience_level": "Student or fresher"},
    )

    assert ranked[0].name == "Fresher Programme"


def test_ranking_is_limited_to_five_resources():
    resources = [
        resource(str(index), "Employment", "job career support", "job")
        for index in range(8)
    ]

    ranked = rank_resources("I need a job", "employment", resources)

    assert len(ranked) == 5


def test_final_score_is_weighted_and_bounded():
    score = calculate_final_score(1.0, 0.5, 0.0)

    assert score == 0.5
    assert 0.0 <= score <= 1.0


def test_ranked_results_include_score_and_reason():
    ranked = rank_resources_with_scores(
        "I need a scholarship",
        "education",
        [resource("Scholarship Centre", "Education", "Scholarship support", "scholarship")],
        category="education",
    )

    assert 0.0 <= ranked[0]["score"] <= 1.0
    assert ranked[0]["reason"].startswith("Recommended because")


def test_full_pipeline_detects_intent_scores_and_explains_result():
    resources = [
        resource("Scholarship Centre", "Education", "Scholarship and education support", "scholarship, education"),
        resource("Job Placement", "Employment", "Job placement support", "job, employment"),
    ]

    result = run_recommendation_pipeline(
        "I need a scholarship",
        resources,
        category="education",
        preferences={"support_type": "Scholarship"},
        language="English",
    )

    assert result["intent"] == "education"
    assert 0.0 <= result["match_score"] <= 1.0
    assert result["recommendations"][0]["resource"].name == "Scholarship Centre"
    assert result["recommendations"][0]["reason"].startswith("Recommended because")


def test_invalid_weights_are_rejected():
    with pytest.raises(ValueError, match="positive total"):
        calculate_final_score(1.0, 1.0, 1.0, {"intent": 0, "similarity": 0, "preference": 0})
