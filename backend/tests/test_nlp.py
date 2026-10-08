# test_nlp.py — pytest tests for NLP preprocessing + intent classification
#
# Run from the backend/ directory:
#   pytest tests/test_nlp.py -v

import sys
import os

# Allow imports from app/ without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.nlp_service import preprocess_text, get_tokens, classify_intent


# ── preprocess_text — edge cases ─────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_string_returns_empty(self):
        assert preprocess_text("") == ""

    def test_whitespace_only_returns_empty(self):
        assert preprocess_text("     ") == ""

    def test_newline_only_returns_empty(self):
        assert preprocess_text("\n\t\r") == ""

    def test_punctuation_only_returns_empty(self):
        assert preprocess_text("!!! ??? ...") == ""

    def test_single_stopword_returns_empty(self):
        # "I" is a stop word — nothing meaningful should remain
        assert preprocess_text("I") == ""

    def test_none_returns_empty(self):
        assert preprocess_text(None) == ""

    def test_tabs_and_repeated_spaces_are_normalized(self):
        assert preprocess_text("  I   need\tlegal   help  ") == "need legal help"


# ── preprocess_text — stopword removal ───────────────────────────────────────

class TestStopwordRemoval:

    def test_common_stopwords_removed(self):
        # "I", "a", "the", "is", "in" are all stop words
        result = preprocess_text("I need a job in the city")
        words = result.split()
        assert "i" not in words
        assert "a" not in words
        assert "the" not in words
        assert "in" not in words

    def test_meaningful_words_kept(self):
        result = preprocess_text("I need help finding a job in Pune")
        assert "need" in result
        assert "help" in result

    def test_output_does_not_start_with_stopword(self):
        result = preprocess_text("I am looking for legal help")
        words = result.split()
        # "I" and "am" are stop words — output should not begin with either
        assert words[0] not in ("i", "am")


# ── preprocess_text — punctuation removal ────────────────────────────────────

class TestPunctuationRemoval:

    def test_period_removed(self):
        result = preprocess_text("I need legal help.")
        assert "." not in result

    def test_question_mark_removed(self):
        result = preprocess_text("Where can I get legal advice?")
        assert "?" not in result

    def test_exclamation_removed(self):
        result = preprocess_text("Help me find a job!")
        assert "!" not in result

    def test_comma_removed(self):
        result = preprocess_text("I need health, legal, and career support.")
        assert "," not in result

    def test_multiple_punctuation_removed(self):
        result = preprocess_text("Help!!! I need... support, URGENTLY!")
        assert "!" not in result
        assert "." not in result
        assert "," not in result
        assert result != ""   # meaningful words should still be present

    def test_mixed_case_with_punctuation_is_normalized(self):
        assert preprocess_text("LEGAL!!! Help... URGENT?") == "legal help urgent"


# ── preprocess_text — lemmatization ─────────────────────────────────────────

class TestLemmatization:

    def test_finding_becomes_find(self):
        result = preprocess_text("I am finding a job")
        assert "find" in result
        assert "finding" not in result

    def test_jobs_becomes_job(self):
        result = preprocess_text("There are many jobs available")
        assert "job" in result
        assert "jobs" not in result

    def test_services_becomes_service(self):
        result = preprocess_text("I need counselling services")
        assert "service" in result
        assert "services" not in result

    def test_women_becomes_woman(self):
        # spaCy lemmatizes "women" → "woman"
        result = preprocess_text("These are services for women")
        assert "woman" in result

    def test_running_becomes_run(self):
        result = preprocess_text("She is running a programme")
        assert "run" in result


# ── preprocess_text — normal sentences ───────────────────────────────────────

class TestNormalSentences:

    def test_employment_sentence(self):
        result = preprocess_text("I need help finding a job in Pune.")
        assert result != ""
        assert "find" in result or "job" in result

    def test_legal_sentence(self):
        result = preprocess_text("Where can I get free legal advice for domestic violence?")
        assert "legal" in result
        assert "advice" in result or "violence" in result

    def test_health_sentence(self):
        result = preprocess_text("I am looking for free healthcare and counselling services.")
        assert "healthcare" in result or "counsel" in result

    def test_shelter_sentence(self):
        result = preprocess_text("I need emergency shelter and safety support.")
        assert "shelter" in result or "emergency" in result or "support" in result

    def test_output_is_lowercase(self):
        # All output should be lowercase (applied before spaCy processing)
        result = preprocess_text("I Need LEGAL Help In PUNE")
        assert result == result.lower()

    def test_output_has_no_extra_spaces(self):
        result = preprocess_text("I need help finding a job")
        # No leading, trailing or double spaces
        assert result == result.strip()
        assert "  " not in result

    def test_short_query_keeps_meaningful_word(self):
        assert preprocess_text("Jobs") == "job"

    def test_short_query_with_stopwords_keeps_content(self):
        assert preprocess_text("Need help") == "need help"


# ── get_tokens — return type ─────────────────────────────────────────────────

class TestGetTokens:

    def test_returns_list(self):
        result = get_tokens("I need a job")
        assert isinstance(result, list)

    def test_empty_input_returns_empty_list(self):
        assert get_tokens("") == []

    def test_whitespace_returns_empty_list(self):
        assert get_tokens("   ") == []

    def test_tokens_are_strings(self):
        tokens = get_tokens("I need legal help")
        assert all(isinstance(t, str) for t in tokens)

    def test_tokens_match_preprocess_words(self):
        # get_tokens and preprocess_text must be consistent
        tokens = get_tokens("I need help finding a job")
        joined = preprocess_text("I need help finding a job")
        assert " ".join(tokens) == joined


# ── Helper ────────────────────────────────────────────────────────────────────

def intent_of(text: str) -> str:
    """Shorthand — returns just the intent string."""
    return classify_intent(text)["intent"]


def confidence_of(text: str) -> float:
    """Shorthand — returns just the confidence value."""
    return classify_intent(text)["confidence"]


# ── classify_intent — return structure ───────────────────────────────────────

class TestClassifyIntentReturnStructure:

    def test_returns_dict(self):
        result = classify_intent("I need a job")
        assert isinstance(result, dict)

    def test_has_intent_key(self):
        result = classify_intent("I need a job")
        assert "intent" in result

    def test_has_confidence_key(self):
        result = classify_intent("I need a job")
        assert "confidence" in result

    def test_intent_is_string(self):
        result = classify_intent("I need a job")
        assert isinstance(result["intent"], str)

    def test_confidence_is_float(self):
        result = classify_intent("I need a job")
        assert isinstance(result["confidence"], float)

    def test_confidence_between_0_and_1(self):
        result = classify_intent("I need legal advice from a lawyer")
        assert 0.0 <= result["confidence"] <= 1.0


# ── classify_intent — edge cases ─────────────────────────────────────────────

class TestClassifyIntentEdgeCases:

    def test_empty_string_returns_general(self):
        assert intent_of("") == "general"

    def test_whitespace_returns_general(self):
        assert intent_of("   ") == "general"

    def test_punctuation_only_returns_general(self):
        assert intent_of("!!!") == "general"

    def test_unknown_word_returns_general(self):
        assert intent_of("abcdefgh xyz") == "general"

    def test_single_stopword_returns_general(self):
        assert intent_of("I") == "general"

    def test_general_confidence_is_zero(self):
        assert confidence_of("hello") == 0.0

    def test_empty_confidence_is_zero(self):
        assert confidence_of("") == 0.0


# ── classify_intent — case insensitivity ─────────────────────────────────────

class TestClassifyIntentCaseInsensitivity:

    def test_uppercase_legal(self):
        assert intent_of("LEGAL ADVICE COURT LAWYER") == "legal"

    def test_uppercase_healthcare(self):
        assert intent_of("HOSPITAL DOCTOR MEDICAL") == "healthcare"

    def test_mixed_case_employment(self):
        assert intent_of("I Need A JOB And Career Guidance") == "employment"

    def test_mixed_case_counselling(self):
        assert intent_of("I Need COUNSELLING For DEPRESSION") == "counselling"


# ── classify_intent — emergency ──────────────────────────────────────────────

class TestIntentEmergency:

    def test_police_danger(self):
        assert intent_of("There is a dangerous attack, I need police immediately") == "emergency"

    def test_sos_urgent(self):
        assert intent_of("SOS! Danger, send help urgently") == "emergency"

    def test_confidence_greater_than_zero(self):
        assert confidence_of("police attack danger") > 0.0

    def test_crisis_threat(self):
        assert intent_of("I am in a crisis, there is a threat") == "emergency"


# ── classify_intent — legal ───────────────────────────────────────────────────

class TestIntentLegal:

    def test_lawyer_divorce(self):
        assert intent_of("I need a lawyer for my divorce case") == "legal"

    def test_fir_rights(self):
        assert intent_of("How do I file an FIR and understand my rights?") == "legal"

    def test_multiple_legal_keywords(self):
        assert intent_of("I need legal advice, court help, and bail information") == "legal"

    def test_confidence_greater_than_zero(self):
        assert confidence_of("I need a lawyer") > 0.0


# ── classify_intent — healthcare ─────────────────────────────────────────────

class TestIntentHealthcare:

    def test_hospital_medical(self):
        assert intent_of("I need to visit the hospital for medical treatment") == "healthcare"

    def test_doctor_nutrition(self):
        assert intent_of("Where can I find a doctor and get nutrition advice?") == "healthcare"

    def test_pregnancy(self):
        assert intent_of("I need maternal care and pregnancy support") == "healthcare"

    def test_confidence_greater_than_zero(self):
        assert confidence_of("hospital doctor") > 0.0


# ── classify_intent — counselling ────────────────────────────────────────────

class TestIntentCounselling:

    def test_depression_anxiety(self):
        assert intent_of("I want counselling for depression and anxiety") == "counselling"

    def test_stress_mental_health(self):
        assert intent_of("I feel stressed and need mental health support") == "counselling"

    def test_multiple_keywords(self):
        assert intent_of("depression anxiety trauma mental health therapy") == "counselling"

    def test_confidence_greater_than_zero(self):
        assert confidence_of("I need counselling") > 0.0


# ── classify_intent — domestic_violence ──────────────────────────────────────

class TestIntentDomesticViolence:

    def test_abusive_husband(self):
        assert intent_of("My husband is abusive and beats me at home") == "domestic_violence"

    def test_escape_violence(self):
        assert intent_of("I want to escape domestic violence and harassment") == "domestic_violence"

    def test_dowry_torture(self):
        assert intent_of("I am facing dowry harassment and torture at home") == "domestic_violence"

    def test_confidence_greater_than_zero(self):
        assert confidence_of("domestic violence abuse") > 0.0


# ── classify_intent — employment ─────────────────────────────────────────────

class TestIntentEmployment:

    def test_job_pune(self):
        assert intent_of("I need help finding a job in Pune") == "employment"

    def test_vocational_career(self):
        assert intent_of("I want vocational training and career guidance") == "employment"

    def test_salary_hire(self):
        assert intent_of("I am looking for a job with a good salary") == "employment"

    def test_confidence_greater_than_zero(self):
        assert confidence_of("I need a job") > 0.0

    def test_hindi_job_query(self):
        assert intent_of("मुझे नौकरी चाहिए") == "employment"

    def test_marathi_job_query(self):
        assert intent_of("मला नोकरी हवी आहे") == "employment"

    def test_mixed_english_hindi_job_query(self):
        assert intent_of("मुझे job चाहिए") == "employment"


# ── classify_intent — education ──────────────────────────────────────────────

class TestIntentEducation:

    def test_scholarship_college(self):
        assert intent_of("I want a scholarship to study at college") == "education"

    def test_literacy_training(self):
        assert intent_of("Where can I find free literacy and training courses?") == "education"

    def test_university_admission(self):
        assert intent_of("I need help with university admission and fees") == "education"

    def test_confidence_greater_than_zero(self):
        assert confidence_of("I want to study and get a scholarship") > 0.0

    def test_hindi_scholarship_query(self):
        assert intent_of("मुझे छात्रवृत्ति चाहिए") == "education"

    def test_marathi_scholarship_query(self):
        assert intent_of("मला शिष्यवृत्ती हवी आहे") == "education"


# ── classify_intent — government_scheme ──────────────────────────────────────

class TestIntentGovernmentScheme:

    def test_welfare_schemes_yojana(self):
        assert intent_of("Tell me about government welfare schemes and yojana") == "government_scheme"

    def test_subsidy_grant(self):
        assert intent_of("How do I apply for a government subsidy or grant?") == "government_scheme"

    def test_pension_ration(self):
        assert intent_of("I want to register for pension and ration benefits") == "government_scheme"

    def test_confidence_greater_than_zero(self):
        assert confidence_of("government scheme welfare") > 0.0


# ── classify_intent — financial_support ──────────────────────────────────────

class TestIntentFinancialSupport:

    def test_loan_financial(self):
        assert intent_of("I need a loan and financial support for my business") == "financial_support"

    def test_afford_economic(self):
        assert intent_of("I cannot afford the fees and need economic help") == "financial_support"

    def test_poverty_credit(self):
        assert intent_of("I am in poverty and need microfinance credit") == "financial_support"

    def test_confidence_greater_than_zero(self):
        assert confidence_of("I need financial support") > 0.0


# ── classify_intent — shelter ────────────────────────────────────────────────

class TestIntentShelter:

    def test_safe_shelter_accommodation(self):
        assert intent_of("I need a safe shelter and accommodation urgently") == "shelter"

    def test_refuge_hostel(self):
        assert intent_of("Where is the nearest women refuge or hostel?") == "shelter"

    def test_safe_house(self):
        assert intent_of("I need a safe house and place to live") == "shelter"

    def test_confidence_greater_than_zero(self):
        assert confidence_of("I need shelter") > 0.0
