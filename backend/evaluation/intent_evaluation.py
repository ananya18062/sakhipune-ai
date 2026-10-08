"""Project evaluation data and metrics for SakhiPune AI intent classification.

This is a small, hand-written evaluation set for project validation only. It is
not a training dataset and is not intended to represent a large external corpus.
Run from backend/: python evaluation/intent_evaluation.py
"""

import os
import sys

from sklearn.metrics import accuracy_score, classification_report, precision_recall_fscore_support

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.nlp_service import classify_intent


# Project evaluation data: representative queries with expected classifier intents.
EVALUATION_DATA = [
    # Employment / jobs
    ("I need a job", "employment"),
    ("I am searching for employment", "employment"),
    ("Can you help me find work?", "employment"),
    # Internships are evaluated against the existing employment intent baseline.
    ("I want an internship in software development", "employment"),
    ("Where can I find a summer internship?", "employment"),
    ("I need an internship opportunity", "employment"),
    # Education
    ("I want to continue my education", "education"),
    ("Help me find a college course", "education"),
    ("I need admission guidance for university", "education"),
    # Scholarships
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
    # Emergency / safety
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


def evaluate_dataset() -> dict:
    """Run the existing classifier and return actual evaluation metrics."""
    texts = [text for text, _ in EVALUATION_DATA]
    expected = [label for _, label in EVALUATION_DATA]
    predicted = [classify_intent(text)["intent"] for text in texts]
    labels = sorted(set(expected) | set(predicted))

    precision, recall, f1, _ = precision_recall_fscore_support(
        expected,
        predicted,
        labels=labels,
        average="macro",
        zero_division=0,
    )
    weighted_precision, weighted_recall, weighted_f1, _ = precision_recall_fscore_support(
        expected,
        predicted,
        labels=labels,
        average="weighted",
        zero_division=0,
    )

    return {
        "count": len(EVALUATION_DATA),
        "accuracy": accuracy_score(expected, predicted),
        "macro_precision": precision,
        "macro_recall": recall,
        "macro_f1": f1,
        "weighted_precision": weighted_precision,
        "weighted_recall": weighted_recall,
        "weighted_f1": weighted_f1,
        "expected": expected,
        "predicted": predicted,
        "labels": labels,
    }


def main() -> None:
    results = evaluate_dataset()
    print("SakhiPune AI intent evaluation (project evaluation data)")
    print(f"Queries evaluated: {results['count']}")
    print(f"Accuracy: {results['accuracy']:.3f}")
    print(f"Macro precision: {results['macro_precision']:.3f}")
    print(f"Macro recall: {results['macro_recall']:.3f}")
    print(f"Macro F1-score: {results['macro_f1']:.3f}")
    print(f"Weighted precision: {results['weighted_precision']:.3f}")
    print(f"Weighted recall: {results['weighted_recall']:.3f}")
    print(f"Weighted F1-score: {results['weighted_f1']:.3f}")
    print("\nPer-intent report:")
    print(classification_report(
        results["expected"],
        results["predicted"],
        labels=results["labels"],
        zero_division=0,
    ))

    mismatches = [
        (text, expected, predicted)
        for (text, expected), predicted in zip(EVALUATION_DATA, results["predicted"])
        if expected != predicted
    ]
    print(f"Mismatches: {len(mismatches)}")
    for text, expected, predicted in mismatches:
        print(f"- {text!r}: expected={expected}, predicted={predicted}")


if __name__ == "__main__":
    main()
