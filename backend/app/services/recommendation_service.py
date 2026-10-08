# recommendation_service.py — Basic intent-to-resource recommendation service
#
# Logic:
#   1. Map the detected intent to a database category name
#   2. Query PostgreSQL for resources in that category
#   3. Return the list of matching SupportResource objects
#
# This is the baseline system — no ML ranking or semantic search yet.

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database.models import SupportResource
from app.services.resource_service import get_all_resources, get_resources_by_category
from app.services.nlp_service import classify_intent, get_tokens
from app.services.tfidf_service import build_resource_text, calculate_similarity, fit_tfidf, transform_query


# ── Intent → category mapping ─────────────────────────────────────────────────
# Maps classifier intent names to the category strings stored in the database.
# Edit this dict to adjust mappings without touching any other logic.

INTENT_TO_CATEGORY: dict[str, str] = {
    "emergency":          "Emergency",
    "legal":              "Legal Support",
    "healthcare":         "Healthcare",
    "counselling":        "Counselling",
    "domestic_violence":  "Domestic Violence Support",
    "employment":         "Employment",
    "education":          "Education",
    "government_scheme":  "Government Schemes",
    "financial_support":  "Financial Support",
    "shelter":            "Shelters",
    "general":            "General",
}

CATEGORY_TO_INTENT: dict[str, str] = {
    "jobs": "employment", "internships": "employment",
    "education": "education", "education_and_scholarships": "education",
    "legal": "legal", "legal_help": "legal", "healthcare": "healthcare",
    "counselling": "counselling", "safety": "emergency",
    "safety_and_emergency": "emergency", "financial_support": "financial_support",
    "shelter": "shelter", "government_scheme": "government_scheme",
    "government_schemes": "government_scheme",
}

DEFAULT_WEIGHTS = {
    "intent": 0.35,
    "similarity": 0.30,
    "category": 0.15,
    "preference": 0.10,
    "location": 0.05,
    "language": 0.05,
}

PREFERENCE_KEYS = {
    "field", "interest_area", "education_level", "experience", "experience_level",
    "support_type", "work_preference", "work_type", "urgency", "assistance_type",
    "next_step", "requirement", "scheme_type", "eligibility_help", "format",
}

LOCATION_SCORES = {
    "pune": 1.0,
    "pimpri-chinchwad": 0.6,
    "pimpri chinchwad": 0.6,
    "nearby maharashtra": 0.6,
    "online": 0.4,
}


def _normalise_category(value: str | None) -> str:
    if not value:
        return ""
    return "_".join(value.lower().replace("&", "and").replace("-", " ").split())


def calculate_final_score(
    intent_score: float,
    similarity_score: float,
    preference_score: float,
    category_score: float = 0.0,
    location_score: float = 0.0,
    language_score: float = 0.0,
    weights: dict[str, float] | None = None,
) -> float:
    """Combine explainable recommendation signals with configurable weights."""
    if isinstance(category_score, dict) and weights is None:
        weights = category_score
        category_score = 0.0
    active_weights = weights or DEFAULT_WEIGHTS
    weight_total = sum(active_weights.values())
    if weight_total <= 0:
        raise ValueError("scoring weights must have a positive total")
    score = (
        intent_score * active_weights.get("intent", 0.0)
        + similarity_score * active_weights.get("similarity", 0.0)
        + category_score * active_weights.get("category", 0.0)
        + preference_score * active_weights.get("preference", 0.0)
        + location_score * active_weights.get("location", 0.0)
        + language_score * active_weights.get("language", 0.0)
    ) / weight_total
    return round(max(0.0, min(1.0, score)), 4)


def _match_score(value: str | None, target: str | None) -> float:
    if not value or not target:
        return 0.0
    value_tokens = set(get_tokens(value))
    target_tokens = set(get_tokens(target))
    return 1.0 if value_tokens and value_tokens.intersection(target_tokens) else 0.0


def calculate_location_score(resource_location: str | None, user_location: str | None = "Pune") -> float:
    """Return a coarse location relevance score for Pune-focused matching.

    The function intentionally works with broad labels only; it does not
    process or require a precise address.
    """
    if not resource_location or not user_location:
        return 0.0

    resource_value = resource_location.strip().lower()
    user_value = user_location.strip().lower()
    if user_value != "pune":
        return 1.0 if resource_value == user_value else 0.0

    if "pune" in resource_value and "pimpri" not in resource_value:
        return LOCATION_SCORES["pune"]
    if "pimpri" in resource_value or "nearby maharashtra" in resource_value:
        return LOCATION_SCORES["nearby maharashtra"]
    if "online" in resource_value:
        return LOCATION_SCORES["online"]
    return 0.0


def _language_code(value: str | None) -> str:
    aliases = {"english": "en", "hindi": "hi", "marathi": "mr"}
    normalized = (value or "").strip().lower()
    return aliases.get(normalized, normalized)


def _preference_score(resource: SupportResource, preferences: dict | None) -> float:
    if not preferences:
        return 0.0
    relevant_values = (
        value for key, value in preferences.items()
        if key in PREFERENCE_KEYS and value
    )
    preference_text = " ".join(str(value) for value in relevant_values)
    preference_tokens = set(get_tokens(preference_text))
    resource_tokens = set(get_tokens(build_resource_text(resource)))
    if not preference_tokens:
        return 0.0
    return len(preference_tokens.intersection(resource_tokens)) / len(preference_tokens)


def rank_resources(
    query: str,
    intent: str,
    resources: list[SupportResource],
    category: str | None = None,
    preferences: dict | None = None,
    location: str | None = None,
    language: str | None = None,
    weights: dict[str, float] | None = None,
    limit: int = 5,
) -> list[SupportResource]:
    """Rank candidates using intent/category, TF-IDF, and preference signals."""
    return [item["resource"] for item in rank_resources_with_scores(
        query, intent, resources, category, preferences, location, language, weights, limit
    )]


def rank_resources_with_scores(
    query: str,
    intent: str,
    resources: list[SupportResource],
    category: str | None = None,
    preferences: dict | None = None,
    location: str | None = None,
    language: str | None = None,
    weights: dict[str, float] | None = None,
    limit: int = 5,
) -> list[dict]:
    """Return ranked resource details with transparent score and reason."""
    if not resources or limit <= 0:
        return []
    usable = [(resource, build_resource_text(resource)) for resource in resources]
    usable = [(resource, text) for resource, text in usable if text]
    if not usable:
        return []
    try:
        vectorizer, resource_vectors = fit_tfidf([text for _, text in usable])
        query_vector = transform_query(vectorizer, query)
    except ValueError:
        return [{"resource": resource, "score": 0.0, "reason": "Recommended because it matches your support request."} for resource, _ in usable[:limit]]

    requested_intent = CATEGORY_TO_INTENT.get(_normalise_category(category), intent)
    expected_category = INTENT_TO_CATEGORY.get(requested_intent, "")
    scored_resources = []
    for index, (resource, _) in enumerate(usable):
        resource_category = (resource.category or "").strip().lower()
        intent_score = 1.0 if resource_category in {
            expected_category.lower(), requested_intent.lower()
        } else 0.0
        selected_category = _normalise_category(category)
        category_score = _match_score(resource.category, selected_category.replace("_", " "))
        similarity_score = calculate_similarity(query_vector, resource_vectors[index])
        preference_score = _preference_score(resource, preferences)
        requested_location = location or (preferences or {}).get("location") or "Pune"
        requested_language = language or (preferences or {}).get("language")
        location_score = calculate_location_score(getattr(resource, "location", None), requested_location)
        language_score = 1.0 if (
            requested_language
            and _language_code(getattr(resource, "language", None)) == _language_code(requested_language)
        ) else 0.0
        final_score = calculate_final_score(
            intent_score,
            similarity_score,
            preference_score,
            category_score,
            location_score,
            language_score,
            weights,
        )
        reasons = []
        if intent_score:
            reasons.append("matches your support need")
        if category_score:
            reasons.append("matches your selected category")
        if similarity_score >= 0.2:
            reasons.append("matches your request text")
        if preference_score:
            reasons.append("matches your preferences")
        if location_score:
            reasons.append("matches your location preference")
        if language_score:
            reasons.append("matches your language preference")
        reason = "Recommended because it " + ", ".join(reasons[:2] or ["is relevant to your request"]) + "."
        scored_resources.append((final_score, similarity_score, resource, reason))

    scored_resources.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [
        {"resource": resource, "score": score, "reason": reason}
        for score, _, resource, reason in scored_resources[:limit]
    ]


def run_recommendation_pipeline(
    query: str,
    resources: list[SupportResource],
    category: str | None = None,
    preferences: dict | None = None,
    location: str | None = None,
    language: str | None = None,
    limit: int = 5,
) -> dict:
    """Run the complete explainable recommendation pipeline in one place.

    The intent classifier remains the baseline NLP step. Ranking then combines
    TF-IDF/cosine similarity, category, preferences, location, and language.
    ``match_score`` is a ranking score, never a probability.
    """
    nlp_result = classify_intent(query)
    ranked = rank_resources_with_scores(
        query,
        nlp_result["intent"],
        resources,
        category=category,
        preferences=preferences,
        location=location,
        language=language,
        limit=limit,
    )
    return {
        "intent": nlp_result["intent"],
        "confidence": nlp_result["confidence"],
        "match_score": ranked[0]["score"] if ranked else 0.0,
        "recommendations": ranked,
    }


# ── Main function ─────────────────────────────────────────────────────────────

def get_recommendations(
    db: Session,
    intent: str,
    query: str | None = None,
    category: str | None = None,
    preferences: dict | None = None,
    location: str | None = None,
    language: str | None = None,
    limit: int = 5,
) -> list[SupportResource]:
    """
    Returns a list of SupportResource rows matching the given intent.

    Steps:
      1. Look up the category name for the intent.
      2. Query the database for resources in that category.
      3. Return the list (may be empty if no resources exist yet).

    Returns an empty list if:
      - The intent is not recognised.
      - No resources exist for the category.
      - The database is unavailable.

    No exceptions are raised to the caller — failures are handled
    internally and logged to stdout.

    Example:
        resources = get_recommendations(db, "employment")
        # → [<SupportResource name="Pune Women Skill Centre" ...>, ...]
    """
    # Step 1: resolve intent to a category name
    category = INTENT_TO_CATEGORY.get(intent)

    if not category:
        # Unknown intent — return empty list, do not crash
        print(f"INFO: No category mapping found for intent '{intent}'")
        return []

    # Step 2: query the database and optionally rank all candidates.
    try:
        if query:
            resources = get_all_resources(db)
            return rank_resources(
                query, intent, resources, category, preferences,
                location, language, limit=limit,
            )
        return get_resources_by_category(db, category)[:limit]

    except SQLAlchemyError as e:
        # Database error — log it and return empty list gracefully
        print(f"WARNING: Database query failed for category '{category}': {e.__class__.__name__}")
        return []


def get_ranked_recommendations(
    db: Session,
    query: str,
    intent: str | None = None,
    category: str | None = None,
    preferences: dict | None = None,
    location: str | None = None,
    language: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Fetch candidates and return ranked resources with score metadata."""
    try:
        resources = get_all_resources(db)
        if intent is None:
            return run_recommendation_pipeline(
                query, resources, category, preferences, location, language, limit
            )["recommendations"]
        return rank_resources_with_scores(
            query, intent, resources, category, preferences,
            location, language, limit=limit,
        )
    except SQLAlchemyError as error:
        print(f"WARNING: Ranked resource query failed: {error.__class__.__name__}")
        return []


# ── Helper: convert ORM object to plain dict ──────────────────────────────────

def resource_to_dict(resource: SupportResource) -> dict:
    """
    Converts a SupportResource ORM object to a plain dictionary.
    Used when returning results via the API.

    Example output:
        {
            "id": 1,
            "name": "Pune Women Skill Centre",
            "category": "Employment",
            "description": "Free skill development programmes.",
            "location": "Shivajinagar, Pune",
            "contact": "+91-20-12345678",
            "language": "en",
            "keywords": "job,career,skill"
        }
    """
    return {
        "id":          resource.id,
        "name":        resource.name,
        "category":    resource.category,
        "description": resource.description,
        "location":    resource.location,
        "contact":     resource.contact,
        "language":    resource.language,
        "keywords":    resource.keywords,
    }
