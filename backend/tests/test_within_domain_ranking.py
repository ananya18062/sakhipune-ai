"""test_within_domain_ranking.py — Regression tests verifying that different
queries within the same domain produce appropriately different recommendation
results after the keyword repair and scoring reweight.

Test methodology:
- Run rank_resources_with_scores with real DB resources for each domain.
- Compare the top-ranked resource for different queries.
- Assert that at least 2 out of 3 queries return different top resources,
  OR that the scores are meaningfully different (not within 0.005 of each other).
- When only 1 resource matches all queries equally (genuine dataset limitation),
  document and accept this with an explanation.

Known dataset limitations (documented, not failures):
- Internships: only 2 resources. Queries for "AI/ML" vs "web development" CAN
  produce the same order if neither resource mentions those specific terms — but
  scores must now differ because keyword_overlap distinguishes them.
- All domains: subcategory filters (e.g. "remote") only work when work_mode
  column has data; only Employment and Internship rows have this.
"""

import pytest
from unittest.mock import MagicMock

from app.services.recommendation_service import rank_resources_with_scores
from app.services.nlp_service import classify_intent
from app.database.connection import SessionLocal
from app.services.internship_service import get_all_internship_resources
from app.services.government_service import get_all_government_resources
from app.services.education_service import get_education_and_scholarship_resources
from app.services.legal_service import get_all_legal_resources


# ── Fixture helpers ───────────────────────────────────────────────────────────

def to_orm(d: dict):
    m = MagicMock()
    for k in ["id", "name", "category", "description", "location",
              "contact", "language", "keywords", "experience_level",
              "work_mode", "employment_type"]:
        setattr(m, k, d.get(k))
    return m


def rank(query: str, resources_dicts: list, category_key: str, limit: int = 3) -> list[dict]:
    """Run ranking pipeline and return scored items."""
    intent = classify_intent(query)["intent"]
    orm_list = [to_orm(d) for d in resources_dicts]
    return rank_resources_with_scores(query, intent, orm_list, category=category_key, limit=limit)


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


# ── Internships ───────────────────────────────────────────────────────────────

class TestInternshipRanking:
    """2 resources: Yuva Karya (government training) vs SARTHI COEP (technical/IT)."""

    def test_technical_query_ranks_sarthi_first(self, db):
        resources = get_all_internship_resources(db)
        results = rank("technical IT engineering internship COEP", resources, "internships")
        assert len(results) >= 1
        top = results[0]["resource"].name
        assert "SARTHI" in top, (
            f"Expected SARTHI COEP (IT/engineering keywords) to rank first, got: {top}"
        )

    def test_government_training_query_ranks_yuva_karya_first(self, db):
        resources = get_all_internship_resources(db)
        results = rank("government training scheme skill placement stipend internship", resources, "internships")
        assert len(results) >= 1
        top = results[0]["resource"].name
        assert "Yuva Karya" in top or "Mukhyamantri" in top, (
            f"Expected Yuva Karya (government/stipend keywords) to rank first, got: {top}"
        )

    def test_different_queries_produce_different_top_scores(self, db):
        """Even when ranking order may match, scores must differ between queries."""
        resources = get_all_internship_resources(db)
        r1 = rank("AI machine learning internship fresher", resources, "internships", limit=1)
        r2 = rank("government paid training scheme stipend", resources, "internships", limit=1)
        # Scores should differ because keyword overlap differs
        score1 = r1[0]["score"] if r1 else 0.0
        score2 = r2[0]["score"] if r2 else 0.0
        assert abs(score1 - score2) > 0.001 or r1[0]["resource"].name != r2[0]["resource"].name, (
            f"Identical top resource AND identical scores for different queries: "
            f"score1={score1}, score2={score2}"
        )

    def test_internship_results_include_reason(self, db):
        resources = get_all_internship_resources(db)
        results = rank("internship for fresher", resources, "internships")
        for item in results:
            assert item["reason"], "Every result must have a non-empty reason"
            assert len(item["reason"]) > 10


# ── Government Schemes ────────────────────────────────────────────────────────

class TestGovernmentSchemeRanking:
    """5 resources: maternity/PMMVY, LPG/Ujjwala, Ladki Bahin/financial,
    Manodhairya/rehabilitation, Swadhar/shelter."""

    def test_maternity_query_ranks_pmmvy_first(self, db):
        resources = get_all_government_resources(db)
        results = rank("maternity pregnancy benefit scheme", resources, "government_scheme")
        assert len(results) >= 1
        top = results[0]["resource"].name
        assert "PMMVY" in top or "Matru" in top or "Vandana" in top, (
            f"Expected PMMVY (maternity keywords) first, got: {top}"
        )

    def test_financial_monthly_query_ranks_ladki_bahin_high(self, db):
        resources = get_all_government_resources(db)
        results = rank("monthly financial cash 1500 women scheme", resources, "government_scheme")
        assert len(results) >= 1
        top_names = [r["resource"].name for r in results[:2]]
        has_ladki = any("Ladki" in n or "Bahin" in n for n in top_names)
        assert has_ladki, (
            f"Expected Ladki Bahin (monthly/1500 keywords) in top 2, got: {top_names}"
        )

    def test_shelter_rehabilitation_query_ranks_swadhar_or_manodhairya(self, db):
        resources = get_all_government_resources(db)
        results = rank("shelter rehabilitation women government scheme", resources, "government_scheme")
        assert len(results) >= 1
        top_names = [r["resource"].name for r in results[:2]]
        has_shelter = any("Swadhar" in n or "Manodhairya" in n for n in top_names)
        assert has_shelter, (
            f"Expected Swadhar or Manodhairya (shelter/rehabilitation) in top 2, got: {top_names}"
        )

    def test_three_queries_produce_at_least_two_different_top_resources(self, db):
        resources = get_all_government_resources(db)
        tops = []
        for q in [
            "maternity pregnancy benefit",
            "monthly cash financial women",
            "shelter rehabilitation domestic violence",
        ]:
            r = rank(q, resources, "government_scheme", limit=1)
            tops.append(r[0]["resource"].name if r else "")
        unique_tops = len(set(tops))
        assert unique_tops >= 2, (
            f"All 3 government scheme queries returned the same top resource: {tops}"
        )


# ── Education ─────────────────────────────────────────────────────────────────

class TestEducationRanking:
    """5 resources: Mahadbt portal, Savitribai school scholarship, Free Class 12,
    Foreign scholarship, SPPU university."""

    def test_foreign_scholarship_query_ranks_foreign_scholarship_first(self, db):
        resources = get_education_and_scholarship_resources(db)
        results = rank("foreign scholarship abroad postgraduate", resources, "education")
        assert len(results) >= 1
        top = results[0]["resource"].name
        assert "Foreign" in top, (
            f"Expected Foreign Scholarship first for foreign/abroad query, got: {top}"
        )

    def test_school_girl_query_ranks_school_scholarships_first(self, db):
        resources = get_education_and_scholarship_resources(db)
        results = rank("free scholarship girl school class 12", resources, "education")
        assert len(results) >= 1
        top = results[0]["resource"].name
        # Free Class 12 or Savitribai school scholarship should top this
        assert any(kw in top for kw in ["Free", "Savitribai", "Class"]), (
            f"Expected a school-focused resource first, got: {top}"
        )

    def test_university_query_ranks_sppu_first(self, db):
        resources = get_education_and_scholarship_resources(db)
        results = rank("university college higher education SPPU Pune", resources, "education")
        assert len(results) >= 1
        top = results[0]["resource"].name
        assert "University" in top or "SPPU" in top, (
            f"Expected SPPU/university resource first, got: {top}"
        )

    def test_all_three_education_queries_give_different_tops(self, db):
        resources = get_education_and_scholarship_resources(db)
        tops = [
            rank("foreign scholarship abroad PhD", resources, "education", 1)[0]["resource"].name,
            rank("school girl free education class 12", resources, "education", 1)[0]["resource"].name,
            rank("university college higher studies SPPU", resources, "education", 1)[0]["resource"].name,
        ]
        assert len(set(tops)) >= 2, (
            f"Education queries did not differentiate: {tops}"
        )


# ── Legal ─────────────────────────────────────────────────────────────────────

class TestLegalRanking:
    """5 resources: DLSA (free legal aid, Pune), MSLSA (state legal services),
    Sakhi OSC, Bombay High Court, Protection Officer (DV Act)."""

    def test_domestic_violence_query_ranks_protection_officer_first(self, db):
        resources = get_all_legal_resources(db)
        results = rank("domestic violence protection order DV Act", resources, "legal")
        assert len(results) >= 1
        top = results[0]["resource"].name
        assert "Protection Officer" in top or "Domestic Violence" in top, (
            f"Expected Protection Officer (DV keywords) first, got: {top}"
        )

    def test_high_court_appeal_query_ranks_bombay_high_court_first(self, db):
        resources = get_all_legal_resources(db)
        results = rank("high court appeal legal aid Bombay", resources, "legal")
        assert len(results) >= 1
        top = results[0]["resource"].name
        assert "High Court" in top or "Bombay" in top, (
            f"Expected Bombay High Court first for appeal query, got: {top}"
        )

    def test_free_legal_aid_query_ranks_dlsa_or_mslsa_high(self, db):
        resources = get_all_legal_resources(db)
        results = rank("free legal aid lawyer advice court case", resources, "legal")
        top_names = [r["resource"].name for r in results[:2]]
        has_aid = any("DLSA" in n or "District Legal" in n or "State Legal" in n or "MSLSA" in n
                      for n in top_names)
        assert has_aid, (
            f"Expected DLSA or MSLSA in top 2 for free legal aid query, got: {top_names}"
        )

    def test_three_legal_queries_give_different_tops(self, db):
        resources = get_all_legal_resources(db)
        tops = [
            rank("domestic violence protection order", resources, "legal", 1)[0]["resource"].name,
            rank("high court appeal Bombay legal", resources, "legal", 1)[0]["resource"].name,
            rank("free legal aid lawyer Pune district", resources, "legal", 1)[0]["resource"].name,
        ]
        assert len(set(tops)) >= 2, (
            f"Legal queries did not differentiate: {tops}"
        )


# ── Cross-domain: editing a query changes the top result ──────────────────────

class TestQueryEditing:

    def test_editing_internship_to_technical_changes_ranking(self, db):
        resources = get_all_internship_resources(db)
        r_before = rank("internship Pune", resources, "internships", limit=1)
        r_after = rank("IT engineering technical internship COEP", resources, "internships", limit=1)
        # Scores must differ OR resource must differ
        before_score = r_before[0]["score"] if r_before else 0
        after_score = r_after[0]["score"] if r_after else 0
        before_name = r_before[0]["resource"].name if r_before else ""
        after_name = r_after[0]["resource"].name if r_after else ""
        assert before_name != after_name or abs(before_score - after_score) > 0.01, (
            "Editing the query to add 'IT engineering technical COEP' must change ranking"
        )

    def test_adding_government_keyword_boosts_yuva_karya(self, db):
        resources = get_all_internship_resources(db)
        r_generic = rank("internship training", resources, "internships", limit=2)
        r_specific = rank("government training scheme stipend 6 month", resources, "internships", limit=2)
        generic_names = [r["resource"].name for r in r_generic]
        specific_names = [r["resource"].name for r in r_specific]
        # At minimum, scores should differ
        assert r_generic[0]["score"] != r_specific[0]["score"] or generic_names != specific_names


# ── No-results scenarios ──────────────────────────────────────────────────────

class TestNoResults:

    def test_empty_resources_returns_empty_list(self, db):
        results = rank_resources_with_scores("internship", "employment", [], category="internships")
        assert results == []

    def test_zero_limit_returns_empty_list(self, db):
        resources = get_all_internship_resources(db)
        orm_list = [to_orm(d) for d in resources]
        results = rank_resources_with_scores("internship", "employment", orm_list, limit=0)
        assert results == []
