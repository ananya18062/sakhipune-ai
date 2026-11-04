# routes.py — API route definitions

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.schemas import (
    SupportRequest, UserQuery, IntentResponse,
    RecommendationAPIResponse, RecommendationItem, ChatRequest,
)
from app.services.nlp_service import classify_intent
from app.services.recommendation_service import (
    get_all_resources, resource_to_dict, run_recommendation_pipeline,
)
from app.services.category_router import route_query, describe_route

# ── Per-category sources endpoints ────────────────────────────────────────────
from app.services.education_service   import describe_education_sources
from app.services.jobs_service        import describe_job_sources
from app.services.internship_service  import describe_internship_sources
from app.services.healthcare_service  import describe_healthcare_sources
from app.services.legal_service       import describe_legal_sources
from app.services.financial_service   import describe_financial_sources
from app.services.shelter_service     import describe_shelter_sources
from app.services.emergency_service   import describe_emergency_sources
from app.services.counselling_service import describe_counselling_sources
from app.services.government_service  import describe_government_sources

# ── Per-category resource loaders (used directly by category endpoints) ───────
from app.services.education_service   import get_education_and_scholarship_resources
from app.services.jobs_service        import get_all_employment_resources
from app.services.internship_service  import get_all_internship_resources
from app.services.healthcare_service  import get_all_healthcare_resources
from app.services.legal_service       import get_all_legal_resources
from app.services.financial_service   import get_all_financial_resources
from app.services.shelter_service     import get_all_shelter_resources
from app.services.emergency_service   import get_all_emergency_resources
from app.services.counselling_service import get_all_counselling_resources
from app.services.api_availability import get_availability
from app.services.resource_normalizer import orm_to_normalized
from app.services.government_service  import get_all_government_resources

from app.database.connection import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def error_response(status_code: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error, "message": message})


def _dict_to_orm(d: dict):
    from app.database.models import SupportResource as _SR
    r = _SR()
    r.id          = 0
    r.name        = d.get("name", "")
    r.category    = d.get("category", "")
    r.description = d.get("description", "")
    r.location    = d.get("location", "")
    r.contact     = d.get("contact", "")
    r.language    = d.get("language", "en")
    # keywords is preserved from the normalized dict so the TF-IDF scorer
    # (tfidf_service.build_resource_text) reads real keyword tokens rather
    # than an empty string when processing category-service results
    r.keywords    = d.get("keywords", "")
    # Structured filter metadata — preserved for service-layer filter logic
    r.experience_level = d.get("experience_level")
    r.work_mode        = d.get("work_mode")
    r.employment_type  = d.get("employment_type")
    return r


def _build_items(pipeline: dict, name_to_meta: dict) -> list[RecommendationItem]:
    items = []
    for item in pipeline["recommendations"]:
        base = resource_to_dict(item["resource"])
        meta = name_to_meta.get(base["name"], {})
        items.append(RecommendationItem(
            id=base.get("id") or 0,
            name=base["name"],
            category=base["category"],
            description=base.get("description"),
            location=base.get("location"),
            contact=meta.get("contact") or base.get("contact"),
            language=base.get("language"),
            score=item["score"],
            reason=item["reason"],
            url=meta.get("url") or meta.get("contact"),
            source=meta.get("source"),
            source_type=meta.get("source_type"),
            last_updated=meta.get("last_updated"),
            is_live=meta.get("is_live", False),
        ))
    return items


def _run_pipeline(
    user_query: SupportRequest,
    raw_resources: list[dict],
    default_category: str,
    endpoint_name: str,
) -> RecommendationAPIResponse:
    """Shared pipeline execution used by every category endpoint."""
    orm_resources = [_dict_to_orm(d) for d in raw_resources]
    try:
        pipeline = run_recommendation_pipeline(
            user_query.message,
            orm_resources,
            category=user_query.category or default_category,
            preferences=user_query.preferences,
            location=(user_query.preferences or {}).get("location"),
            language=user_query.language,
        )
    except Exception:
        logger.exception("Recommendation pipeline failed on /%s", endpoint_name)
        return error_response(500, "RECOMMENDATION_ERROR",
                              "We couldn't build recommendations. Please try again.")

    name_to_meta = {d["name"]: d for d in raw_resources}
    return RecommendationAPIResponse(
        message=user_query.message,
        intent=pipeline["intent"],
        confidence=pipeline["confidence"],
        match_score=pipeline["match_score"],
        recommendations=_build_items(pipeline, name_to_meta),
    )


def _merge_filters_into_preferences(user_query: "SupportRequest") -> dict:
    """Merge structured filter fields into the preferences dict.

    This bridges the gap between the new typed filter fields on SupportRequest
    and the service functions that read them from the preferences dict.
    The preferences dict is used as the shared carrier throughout the pipeline.
    """
    prefs = dict(user_query.preferences or {})
    # Inject structured filters — only when they are actually set
    for attr, key in (
        ("experience_filter",      "experience_filter"),
        ("work_mode_filter",       "work_mode_filter"),
        ("employment_type_filter", "employment_type_filter"),
        ("delivery_mode_filter",   "delivery_mode_filter"),
    ):
        value = getattr(user_query, attr, None)
        if value:
            prefs[key] = value
    return prefs


def _category_endpoint(
    user_query: "SupportRequest",
    db,
    resources_fn,
    default_category: str,
    endpoint_name: str,
    preferences_kwarg: bool = False,
) -> "RecommendationAPIResponse":
    """Fetch resources from a single service then run the pipeline."""
    merged_prefs = _merge_filters_into_preferences(user_query)
    try:
        raw = resources_fn(db, preferences=merged_prefs) \
              if preferences_kwarg else resources_fn(db)
    except SQLAlchemyError:
        logger.exception("Database query failed on /%s", endpoint_name)
        return error_response(503, "SERVICE_UNAVAILABLE",
                              "SakhiPune AI is temporarily unavailable. Please try again shortly.")
    return _run_pipeline(user_query, raw, default_category, endpoint_name)


# ── Core routes ───────────────────────────────────────────────────────────────

@router.get("/")
def root() -> dict:
    return {"message": "Welcome to SakhiPune AI"}


@router.get("/health")
def health_check() -> dict:
    return {"status": "healthy"}


@router.post("/query")
def receive_query(user_query: UserQuery) -> dict:
    return {"message": user_query.message, "language": user_query.language, "status": "received"}


@router.post("/analyze", response_model=IntentResponse)
def analyze_query(user_query: UserQuery) -> IntentResponse:
    try:
        result = classify_intent(user_query.message)
        return IntentResponse(
            message=user_query.message,
            intent=result["intent"],
            confidence=result["confidence"],
        )
    except Exception:
        logger.exception("NLP processing failed on /analyze")
        return error_response(500, "NLP_ERROR", "We couldn't process your request. Please try again.")


# ── /recommend — full-DB cross-category pipeline (unchanged) ─────────────────

@router.post("/recommend", response_model=RecommendationAPIResponse)
def recommend(user_query: SupportRequest, db: Session = Depends(get_db)) -> RecommendationAPIResponse:
    """Full recommendation pipeline across all categories (unchanged behaviour)."""
    try:
        resources = get_all_resources(db)
    except SQLAlchemyError:
        logger.exception("Database query failed on /recommend")
        return error_response(503, "SERVICE_UNAVAILABLE",
                              "SakhiPune AI is temporarily unavailable. Please try again shortly.")
    try:
        pipeline = run_recommendation_pipeline(
            user_query.message, resources,
            category=user_query.category,
            preferences=user_query.preferences,
            location=(user_query.preferences or {}).get("location"),
            language=user_query.language,
        )
    except Exception:
        logger.exception("Recommendation pipeline failed on /recommend")
        return error_response(500, "RECOMMENDATION_ERROR",
                              "We couldn't build recommendations. Please try again.")

    items = []
    for item in pipeline["recommendations"]:
        base   = resource_to_dict(item["resource"])
        normed = orm_to_normalized(item["resource"])
        items.append(RecommendationItem(
            id=base.get("id") or 0,
            name=base["name"],
            category=base["category"],
            description=base.get("description"),
            location=base.get("location"),
            contact=normed.get("contact") or base.get("contact"),
            language=base.get("language"),
            score=item["score"],
            reason=item["reason"],
            url=normed.get("url"),
            source=normed.get("source"),
            source_type=normed.get("source_type"),
            last_updated=normed.get("last_updated"),
            is_live=normed.get("is_live", False),
        ))
    return RecommendationAPIResponse(
        message=user_query.message,
        intent=pipeline["intent"],
        confidence=pipeline["confidence"],
        match_score=pipeline["match_score"],
        recommendations=items,
    )


# ── /route — universal category-routed endpoint ───────────────────────────────

@router.post("/route", response_model=RecommendationAPIResponse)
def route_recommend(user_query: SupportRequest, db: Session = Depends(get_db)) -> RecommendationAPIResponse:
    """
    Universal endpoint.  Detects intent via NLP, routes to the correct
    category service via category_router, then ranks results.

    User Query → NLP → Intent → Category Router → Service → Pipeline → Cards

    Prefer this endpoint for new integrations.  POST /recommend continues to
    work unchanged for backwards compatibility.
    """
    # Step 1: NLP
    try:
        nlp_result = classify_intent(user_query.message)
    except Exception:
        logger.exception("NLP failed on /route")
        return error_response(500, "NLP_ERROR", "We couldn't process your request. Please try again.")

    intent = nlp_result["intent"]

    # Step 2: route to the correct service
    raw_resources, safety_note = route_query(
        intent=intent,
        db=db,
        category=user_query.category,
        preferences=user_query.preferences,
    )

    # Step 3: run the recommendation pipeline
    response = _run_pipeline(user_query, raw_resources, intent, "route")
    if isinstance(response, JSONResponse):
        return response

    # Step 4: attach safety note if present (emergency/shelter/counselling)
    if safety_note and response.recommendations:
        # Prepend note to the first item's reason so it surfaces in the UI
        first = response.recommendations[0]
        first.reason = safety_note + " | " + (first.reason or "")

    return response


# ── /route/explain — which service would handle a query ──────────────────────

@router.get("/route/explain")
def route_explain(intent: str, category: str | None = None) -> dict:
    """Return which service category_router would use for this intent/category."""
    return describe_route(intent, category)


# ── API availability (operator endpoint) ─────────────────────────────────────

@router.get("/api/availability")
def api_availability() -> dict:
    """Return the verified external API availability status for every category.

    This endpoint is for operators / developers only.
    It is never surfaced to end users.

    Response documents which *_API_URL settings are populated,
    which APIs exist and why they are unavailable, and confirms
    that PostgreSQL fallback is active for every category.
    """
    return get_availability()


# ── Education ─────────────────────────────────────────────────────────────────

@router.get("/education/sources")
def education_sources() -> dict:
    return describe_education_sources()

@router.post("/education", response_model=RecommendationAPIResponse)
def education_recommend(user_query: SupportRequest, db: Session = Depends(get_db)):
    return _category_endpoint(user_query, db, get_education_and_scholarship_resources, "education", "education")


# ── Jobs ──────────────────────────────────────────────────────────────────────

@router.get("/jobs/sources")
def jobs_sources() -> dict:
    return describe_job_sources()

@router.post("/jobs", response_model=RecommendationAPIResponse)
def jobs_recommend(user_query: SupportRequest, db: Session = Depends(get_db)):
    return _category_endpoint(user_query, db, get_all_employment_resources,
                               "jobs", "jobs", preferences_kwarg=True)


# ── Internships ───────────────────────────────────────────────────────────────

@router.get("/internships/sources")
def internships_sources() -> dict:
    return describe_internship_sources()

@router.post("/internships", response_model=RecommendationAPIResponse)
def internships_recommend(user_query: SupportRequest, db: Session = Depends(get_db)):
    return _category_endpoint(user_query, db, get_all_internship_resources,
                               "internships", "internships", preferences_kwarg=True)


# ── Healthcare ────────────────────────────────────────────────────────────────

@router.get("/healthcare/sources")
def healthcare_sources() -> dict:
    return describe_healthcare_sources()

@router.post("/healthcare", response_model=RecommendationAPIResponse)
def healthcare_recommend(user_query: SupportRequest, db: Session = Depends(get_db)):
    """Healthcare resources only. Does NOT provide medical advice."""
    return _category_endpoint(user_query, db, get_all_healthcare_resources, "healthcare", "healthcare")


# ── Legal ─────────────────────────────────────────────────────────────────────

@router.get("/legal/sources")
def legal_sources() -> dict:
    return describe_legal_sources()

@router.post("/legal", response_model=RecommendationAPIResponse)
def legal_recommend(user_query: SupportRequest, db: Session = Depends(get_db)):
    """Legal resources only. Does NOT provide legal advice."""
    return _category_endpoint(user_query, db, get_all_legal_resources, "legal", "legal")


# ── Financial Support ─────────────────────────────────────────────────────────

@router.get("/financial/sources")
def financial_sources() -> dict:
    return describe_financial_sources()

@router.post("/financial", response_model=RecommendationAPIResponse)
def financial_recommend(user_query: SupportRequest, db: Session = Depends(get_db)):
    """Financial support resources. Does NOT provide financial advice."""
    return _category_endpoint(user_query, db, get_all_financial_resources,
                               "financial_support", "financial")


# ── Shelter ───────────────────────────────────────────────────────────────────

@router.get("/shelter/sources")
def shelter_sources() -> dict:
    return describe_shelter_sources()

@router.post("/shelter", response_model=RecommendationAPIResponse)
def shelter_recommend(user_query: SupportRequest, db: Session = Depends(get_db)):
    """Shelter resources only. Women in danger: call 100 or 112 immediately."""
    return _category_endpoint(user_query, db, get_all_shelter_resources, "shelter", "shelter")


# ── Emergency ─────────────────────────────────────────────────────────────────

@router.get("/emergency/sources")
def emergency_sources() -> dict:
    return describe_emergency_sources()

@router.post("/emergency", response_model=RecommendationAPIResponse)
def emergency_recommend(user_query: SupportRequest, db: Session = Depends(get_db)):
    """Emergency resource information. For immediate danger call 100 or 112."""
    return _category_endpoint(user_query, db, get_all_emergency_resources, "emergency", "emergency")


# ── Counselling ───────────────────────────────────────────────────────────────

@router.get("/counselling/sources")
def counselling_sources() -> dict:
    return describe_counselling_sources()

@router.post("/counselling", response_model=RecommendationAPIResponse)
def counselling_recommend(user_query: SupportRequest, db: Session = Depends(get_db)):
    """Counselling resource information only. Not a substitute for professional care."""
    return _category_endpoint(user_query, db, get_all_counselling_resources,
                               "counselling", "counselling")


# ── Government Schemes ────────────────────────────────────────────────────────

@router.get("/government/sources")
def government_sources() -> dict:
    return describe_government_sources()

@router.post("/government", response_model=RecommendationAPIResponse)
def government_recommend(user_query: SupportRequest, db: Session = Depends(get_db)):
    return _category_endpoint(user_query, db, get_all_government_resources,
                               "government_scheme", "government")


# ── /chat — conversational endpoint with follow-up context support ────────────

@router.post("/chat", response_model=RecommendationAPIResponse)
def chat_recommend(request: ChatRequest, db: Session = Depends(get_db)) -> RecommendationAPIResponse:
    """
    Conversational recommendation endpoint.

    Supports:
    - Direct natural-language queries
    - Category-selected queries (domain buttons)
    - Follow-up refinements (e.g. "only remote", "I am a fresher")
    - Query editing (replaces previous context)

    When is_followup=True the conversation_state carries the accumulated
    filters from previous turns. New explicit filters override old ones.
    Contradictory filters (e.g. switching domains) are detected and cleared.
    """
    # ── Step 1: Merge conversation state with the new message ─────────────────
    state = dict(request.conversation_state or {})
    merged_prefs = dict(request.preferences or {})

    # Follow-up: merge new explicit filters into accumulated state,
    # giving priority to anything the user says in the new message.
    if request.is_followup and state:
        # Carry forward accumulated filters, but let new prefs override
        for k, v in state.get("filters", {}).items():
            if k not in merged_prefs and v:
                merged_prefs[k] = v

    # ── Step 2: NLP — classify intent from the composed query ─────────────────
    # For follow-ups, prepend relevant prior context to improve classification
    nlp_query = request.message
    if request.is_followup and state.get("last_query"):
        # Build a composite query that includes key prior context
        prior_domain = state.get("intent", "")
        nlp_query = f"{state.get('last_query', '')} {request.message}"

    try:
        nlp_result = classify_intent(nlp_query)
    except Exception:
        logger.exception("NLP failed on /chat")
        return error_response(500, "NLP_ERROR", "We couldn't process your request. Please try again.")

    intent = nlp_result["intent"]

    # If the user explicitly selected a category (domain button),
    # use that as the authoritative routing signal.
    effective_category = request.category

    # If intent changed domain significantly from prior state and no
    # category override was given, clear incompatible filters.
    prior_intent = state.get("intent", "")
    DOMAIN_GROUPS = {
        "employment": {"employment", "education"},
        "legal": {"legal", "domestic_violence"},
        "health": {"healthcare", "counselling"},
        "safety": {"emergency", "shelter", "domestic_violence"},
        "finance": {"financial_support", "government_scheme"},
    }
    def _domain_group(i: str) -> str:
        for g, members in DOMAIN_GROUPS.items():
            if i in members:
                return g
        return i

    if (prior_intent and intent != prior_intent and
            _domain_group(intent) != _domain_group(prior_intent) and
            not effective_category):
        # Domain shift — clear filters that don't apply to the new domain
        for key in ("experience_filter", "work_mode_filter", "employment_type_filter", "delivery_mode_filter"):
            merged_prefs.pop(key, None)

    # ── Step 3: Route to the correct category service ─────────────────────────
    raw_resources, safety_note = route_query(
        intent=intent,
        db=db,
        category=effective_category,
        preferences=merged_prefs,
    )

    # ── Step 4: Run the recommendation pipeline ───────────────────────────────
    support_req = SupportRequest(
        message=request.message,
        category=effective_category,
        preferences=merged_prefs,
        language=request.language,
    )
    response = _run_pipeline(support_req, raw_resources, intent, "chat")
    if isinstance(response, JSONResponse):
        return response

    # ── Step 5: Apply safety note if present ──────────────────────────────────
    if safety_note and response.recommendations:
        first = response.recommendations[0]
        first.reason = safety_note + " | " + (first.reason or "")

    return response
