"""test_nlp_evaluation.py — Day 29 Task 3: NLP Testing

Sections:
  1. Preprocessing tests (normal, empty, whitespace, punctuation, mixed case, repeats)
  2. Intent classification — 13 intents × representative queries
  3. Multilingual keyword tests (English / Hindi / Marathi aliases)
  4. Full evaluation dataset — metrics printed to stdout, all queries asserted

All tests run through pytest so spaCy loads in the pytest process where
the PyTorch DLL issue does not occur.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    precision_recall_fscore_support,
)

from app.services.nlp_service import (
    classify_intent,
    get_tokens,
    preprocess_text,
    INTENT_KEYWORDS,
    MULTILINGUAL_INTENT_KEYWORDS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — Preprocessing
# ─────────────────────────────────────────────────────────────────────────────

class TestPreprocessing:

    # Normal text
    def test_normal_text_returns_lemmatized_tokens(self):
        tokens = get_tokens("I need help finding a job in Pune")
        assert "job" in tokens
        assert "pune" in tokens
        # stop words removed
        assert "i" not in tokens
        assert "a" not in tokens

    # Empty text
    def test_empty_string_returns_empty_list(self):
        assert get_tokens("") == []

    def test_none_raises_or_returns_empty(self):
        # Passing None: the guard `not isinstance(text, str)` catches it
        assert get_tokens(None) == []  # type: ignore

    # Whitespace only
    def test_whitespace_only_returns_empty(self):
        assert get_tokens("   ") == []
        assert get_tokens("\t\n") == []

    # Punctuation only
    def test_punctuation_only_returns_empty(self):
        assert get_tokens("!!!???...") == []

    def test_punctuation_stripped_from_words(self):
        tokens = get_tokens("legal, advice!")
        assert "legal" in tokens
        assert "advice" in tokens

    # Mixed case
    def test_mixed_case_normalised(self):
        t1 = get_tokens("LEGAL HELP")
        t2 = get_tokens("legal help")
        t3 = get_tokens("Legal Help")
        # All should produce the same tokens after lowercasing
        assert set(t1) == set(t2) == set(t3)

    # Repeated words
    def test_repeated_words_handled(self):
        tokens = get_tokens("job job job career career")
        # Tokens list may have duplicates (set is not applied by get_tokens)
        assert "job" in tokens
        assert "career" in tokens

    # Lemmatization
    def test_lemmatization_jobs_to_job(self):
        assert "job" in get_tokens("I need jobs")

    def test_lemmatization_finding_to_find(self):
        assert "find" in get_tokens("finding work")

    def test_lemmatization_hospitals_to_hospital(self):
        assert "hospital" in get_tokens("hospitals in Pune")

    # preprocess_text returns joined string
    def test_preprocess_text_returns_string(self):
        result = preprocess_text("I need legal help")
        assert isinstance(result, str)
        assert "legal" in result

    def test_preprocess_text_empty_returns_empty_string(self):
        assert preprocess_text("") == ""
        assert preprocess_text("   ") == ""


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Intent classification (13 intents)
# ─────────────────────────────────────────────────────────────────────────────

# Each tuple: (query, expected_intent)
INTENT_TEST_CASES = [
    # Emergency / safety
    ("I am in immediate danger",              "emergency"),
    ("Please send police help urgently",      "emergency"),
    ("I need emergency support right now",    "emergency"),
    ("I feel unsafe at my home",              "domestic_violence"),   # unsafe+home → dv correct
    ("There is a threat to my life",          "emergency"),

    # Legal
    ("I need legal advice",                   "legal"),
    ("Can I speak to a lawyer about my rights?", "legal"),
    ("How do I file a complaint?",            "legal"),
    ("I need legal assistance for my case",   "legal"),
    ("I need help with my divorce case",      "legal"),

    # Healthcare
    ("I need to see a doctor",                "healthcare"),
    ("Where is a nearby hospital?",           "healthcare"),
    ("I need medical treatment",              "healthcare"),
    ("I need maternal healthcare",            "healthcare"),
    ("I want antenatal care",                 "healthcare"),

    # Counselling
    ("I need someone to talk to",             "counselling"),
    ("I am feeling anxious and need counselling", "counselling"),
    ("Can I find a mental health therapist?", "counselling"),
    ("I am feeling depressed and sad",        "counselling"),
    ("I need therapy for stress and trauma",  "counselling"),

    # Domestic violence
    ("I need support after domestic violence","domestic_violence"),
    ("My husband is abusive",                 "domestic_violence"),
    ("I am suffering from dowry harassment",  "domestic_violence"),

    # Employment
    ("I need a job",                          "employment"),
    ("I am searching for employment",         "employment"),
    ("Can you help me find work?",            "employment"),
    ("I am looking for job vacancies",        "employment"),

    # Internships (map to employment intent — no separate intent)
    ("I want an internship in software development", "employment"),
    ("Where can I find a summer internship?", "employment"),

    # Education
    ("I want to continue my education",       "education"),
    ("Help me find a college course",         "education"),
    ("I need admission guidance for university", "education"),
    ("I want to study in Pune",               "education"),

    # Scholarship (sub-category of education)
    ("I need a scholarship",                  "education"),
    ("How can I apply for an education grant?", "education"),
    ("Are there scholarships for women students?", "education"),

    # Government scheme
    ("I want to apply for a government scheme", "government_scheme"),
    ("Are there any welfare benefits for me?","government_scheme"),
    ("How do I register for a government programme?", "government_scheme"),

    # Financial support
    ("I need financial assistance",           "financial_support"),
    ("Can I get help with a small loan?",     "financial_support"),
    ("I cannot afford my expenses",           "financial_support"),
    ("I need livelihood support",             "financial_support"),

    # Shelter
    ("I need a safe shelter",                 "shelter"),
    ("Where can I find a place to stay?",     "shelter"),
    ("I need emergency housing",              "shelter"),
    ("I need a refuge from danger",           "shelter"),

    # General (no keywords match)
    ("Hello, I need some information",        "general"),
    ("I am not sure where to begin",          "general"),
    ("What support is available?",            "general"),
    ("xyzabc qwerty",                         "general"),
    ("",                                      "general"),
    ("   ",                                   "general"),
    ("???!!!",                                "general"),
]


@pytest.mark.parametrize("query,expected_intent", INTENT_TEST_CASES)
def test_intent_classification(query, expected_intent):
    result = classify_intent(query)
    assert result["intent"] == expected_intent, (
        f"Query: {query!r}\n"
        f"Expected: {expected_intent}\n"
        f"Got:      {result['intent']}  (confidence={result['confidence']:.2f})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Multilingual keywords (Hindi / Marathi)
# ─────────────────────────────────────────────────────────────────────────────

class TestMultilingual:

    # Employment — Hindi
    def test_hindi_naukri_is_employment(self):
        assert classify_intent("मुझे नौकरी चाहिए")["intent"] == "employment"

    def test_hindi_rojgar_is_employment(self):
        assert classify_intent("रोजगार की तलाश है")["intent"] == "employment"

    def test_hindi_kaam_is_employment(self):
        assert classify_intent("मुझे काम चाहिए")["intent"] == "employment"

    # Employment — Marathi
    def test_marathi_nokri_is_employment(self):
        assert classify_intent("नोकरी कुठे मिळेल")["intent"] == "employment"

    # Education — Hindi
    def test_hindi_scholarship_is_education(self):
        assert classify_intent("छात्रवृत्ति चाहिए")["intent"] == "education"

    def test_hindi_shiksha_is_education(self):
        assert classify_intent("शिक्षा के लिए मदद चाहिए")["intent"] == "education"

    # Education — Marathi
    def test_marathi_shikshan_is_education(self):
        assert classify_intent("शिक्षण हवे आहे")["intent"] == "education"

    # Healthcare — Hindi
    def test_hindi_arogya_is_healthcare(self):
        assert classify_intent("आरोग्य सेवा चाहिए")["intent"] == "healthcare"

    def test_hindi_doctor_is_healthcare(self):
        assert classify_intent("डॉक्टर की जरूरत है")["intent"] == "healthcare"

    # Healthcare — Marathi
    def test_marathi_davakhana_is_healthcare(self):
        assert classify_intent("दवाखाना कुठे आहे")["intent"] == "healthcare"

    # Mixed language
    def test_mixed_hindi_english_job_is_employment(self):
        assert classify_intent("I need नौकरी in Pune")["intent"] == "employment"

    def test_mixed_marathi_english_scholarship_is_education(self):
        assert classify_intent("मला scholarship हवी आहे")["intent"] == "education"

    # Multilingual keywords are in the map
    def test_multilingual_map_has_employment(self):
        assert "employment" in MULTILINGUAL_INTENT_KEYWORDS
        assert len(MULTILINGUAL_INTENT_KEYWORDS["employment"]) >= 4

    def test_multilingual_map_has_education(self):
        assert "education" in MULTILINGUAL_INTENT_KEYWORDS
        assert len(MULTILINGUAL_INTENT_KEYWORDS["education"]) >= 4

    def test_multilingual_map_has_healthcare(self):
        assert "healthcare" in MULTILINGUAL_INTENT_KEYWORDS
        assert len(MULTILINGUAL_INTENT_KEYWORDS["healthcare"]) >= 3


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — Full evaluation dataset with printed metrics
# ─────────────────────────────────────────────────────────────────────────────

# Re-use the existing evaluation dataset
EVAL_DATA = [
    # Employment
    ("I need a job", "employment"),
    ("I am searching for employment", "employment"),
    ("Can you help me find work?", "employment"),
    ("I want an internship in software development", "employment"),
    ("Where can I find a summer internship?", "employment"),
    ("I need an internship opportunity", "employment"),
    # Education
    ("I want to continue my education", "education"),
    ("Help me find a college course", "education"),
    ("I need admission guidance for university", "education"),
    ("I need a scholarship", "education"),
    ("How can I apply for an education grant?", "education"),
    ("I need help paying my tuition fees", "education"),
    # Legal
    ("I need legal advice", "legal"),
    ("Can I speak to a lawyer about my rights?", "legal"),
    ("How do I file a complaint?", "legal"),
    # Healthcare
    ("I need to see a doctor", "healthcare"),
    ("Where is a nearby hospital?", "healthcare"),
    ("I need medical treatment", "healthcare"),
    # Counselling
    ("I need someone to talk to", "counselling"),
    ("I am feeling anxious and need counselling", "counselling"),
    ("Can I find a mental health therapist?", "counselling"),
    # Emergency
    ("I am in immediate danger", "emergency"),
    ("Please send police help urgently", "emergency"),
    ("I need emergency support right now", "emergency"),
    # Financial support
    ("I need financial assistance", "financial_support"),
    ("Can I get help with a small loan?", "financial_support"),
    ("I cannot afford my expenses", "financial_support"),
    # Shelter
    ("I need a safe shelter", "shelter"),
    ("Where can I find a place to stay?", "shelter"),
    ("I need emergency housing", "shelter"),
    # Government schemes
    ("I want to apply for a government scheme", "government_scheme"),
    ("Are there any welfare benefits for me?", "government_scheme"),
    ("How do I register for a government programme?", "government_scheme"),
    # General
    ("Hello, I need some information", "general"),
    ("What support is available?", "general"),
    ("I am not sure where to begin", "general"),
]


def test_evaluation_metrics_and_report(capsys):
    """
    Runs the full evaluation dataset, prints metrics to stdout,
    and asserts that accuracy is at least 0.85.
    """
    texts     = [t for t, _ in EVAL_DATA]
    expected  = [e for _, e in EVAL_DATA]
    predicted = [classify_intent(t)["intent"] for t in texts]

    acc = accuracy_score(expected, predicted)
    labels = sorted(set(expected) | set(predicted))

    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(
        expected, predicted, labels=labels, average="macro", zero_division=0
    )
    w_p, w_r, w_f1, _ = precision_recall_fscore_support(
        expected, predicted, labels=labels, average="weighted", zero_division=0
    )

    report = classification_report(
        expected, predicted, labels=labels, zero_division=0
    )

    mismatches = [
        (text, exp, pred)
        for (text, exp), pred in zip(EVAL_DATA, predicted)
        if exp != pred
    ]

    with capsys.disabled():
        print("\n" + "=" * 60)
        print("SakhiPune AI — NLP Intent Evaluation")
        print("=" * 60)
        print(f"Queries evaluated  : {len(EVAL_DATA)}")
        print(f"Accuracy           : {acc:.3f}  ({acc*100:.1f}%)")
        print(f"Macro Precision    : {macro_p:.3f}")
        print(f"Macro Recall       : {macro_r:.3f}")
        print(f"Macro F1-score     : {macro_f1:.3f}")
        print(f"Weighted Precision : {w_p:.3f}")
        print(f"Weighted Recall    : {w_r:.3f}")
        print(f"Weighted F1-score  : {w_f1:.3f}")
        print()
        print("Per-intent classification report:")
        print(report)
        if mismatches:
            print(f"Misclassified ({len(mismatches)}):")
            for text, exp, pred in mismatches:
                print(f"  - {text!r}")
                print(f"    Expected={exp}  Got={pred}")
        else:
            print("No misclassifications on evaluation dataset.")
        print("=" * 60)

    # Accuracy must be at least 85%
    assert acc >= 0.85, (
        f"Accuracy {acc:.3f} is below threshold 0.85. "
        f"Misclassified: {mismatches}"
    )
