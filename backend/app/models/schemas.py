# schemas.py — Pydantic schemas for API request and response validation
#
# These are pure data structures — no database or NLP logic here.
# Used by FastAPI to validate incoming requests and shape outgoing responses.

from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, Optional


# ── Request schema ────────────────────────────────────────────────────────────

class UserQuery(BaseModel):
    """
    Sent by the frontend when the user submits a query.

    Example:
        {"message": "I need help finding a job", "language": "en"}
    """
    message: str = Field(..., description="The user's question or concern")
    language: Optional[str] = Field(default=None, description="Language code, e.g. 'en'")

    @field_validator("message")
    @classmethod
    def message_must_not_be_empty(cls, value: str) -> str:
        """Reject blank or whitespace-only messages."""
        if not value.strip():
            raise ValueError("message must not be empty or blank")
        return value.strip()


class SupportRequest(BaseModel):
    """
    Structured support request prepared by the frontend question flow.

    This schema is intentionally separate from UserQuery so existing endpoint
    contracts remain unchanged while the structured request is introduced.
    """
    message: str = Field(..., description="The user's question or concern")
    category: Optional[str] = Field(default=None, description="Normalized support category")
    preferences: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional answers collected by the adaptive question flow",
    )
    language: Optional[str] = Field(default=None, description="Language name or code, e.g. 'English'")

    # ── Structured filter parameters ─────────────────────────────────────────
    # Sent directly from the frontend filter dropdowns.
    # Values must match the controlled vocabulary in database/models.py.
    # None / missing = "no filter applied" (show all results).

    experience_filter: Optional[str] = Field(
        default=None,
        description=(
            "Experience level filter for jobs/internships. "
            "One of: fresher, less_than_1, 1_2_years, 3_5_years, 6_10_years, more_than_10, any. "
            "Omit or set to null to show all."
        ),
    )
    work_mode_filter: Optional[str] = Field(
        default=None,
        description=(
            "Work mode filter. One of: remote, hybrid, on_site. "
            "Omit or set to null to show all work modes."
        ),
    )
    employment_type_filter: Optional[str] = Field(
        default=None,
        description=(
            "Employment type filter. One of: full_time, part_time, contract, "
            "apprenticeship, self_employment. Omit or set to null to show all."
        ),
    )
    delivery_mode_filter: Optional[str] = Field(
        default=None,
        description=(
            "Delivery mode for education resources. One of: online, offline, hybrid. "
            "Omit or set to null to show all."
        ),
    )

    @field_validator("message")
    @classmethod
    def support_message_must_not_be_empty(cls, value: str) -> str:
        """Reject blank or whitespace-only support requests."""
        if not value.strip():
            raise ValueError("message must not be empty or blank")
        return value.strip()

    @field_validator("category")
    @classmethod
    def category_must_be_supported(cls, value: Optional[str]) -> Optional[str]:
        """Normalize accepted category labels to frontend-friendly keys."""
        if value is None:
            return None

        normalized = value.strip().lower().replace("&", "and")
        normalized = "_".join(normalized.replace("-", " ").split())
        category_aliases = {
            "job": "jobs",
            "jobs": "jobs",
            "internship": "internships",
            "internships": "internships",
            "education": "education",
            "education_and_scholarships": "education",
            "legal": "legal",
            "legal_help": "legal",
            "health": "healthcare",
            "healthcare": "healthcare",
            "counselling": "counselling",
            "counseling": "counselling",
            "safety": "safety",
            "safety_and_emergency": "safety",
            "financial_support": "financial_support",
            "shelter": "shelter",
            "government_scheme": "government_scheme",
            "government_schemes": "government_scheme",
        }

        if normalized not in category_aliases:
            raise ValueError("category must be a supported SakhiPune category")
        return category_aliases[normalized]

    @field_validator("language")
    @classmethod
    def language_must_be_supported(cls, value: Optional[str]) -> Optional[str]:
        """Normalize the supported language choices to stable language codes."""
        if value is None:
            return None
        language_aliases = {
            "en": "en", "english": "en",
            "hi": "hi", "hindi": "hi",
            "mr": "mr", "marathi": "mr",
        }
        normalized = value.strip().lower()
        if normalized not in language_aliases:
            raise ValueError("language must be English, Hindi, or Marathi")
        return language_aliases[normalized]

    @field_validator("experience_filter", "work_mode_filter", "employment_type_filter", "delivery_mode_filter")
    @classmethod
    def filter_values_are_safe(cls, value: Optional[str]) -> Optional[str]:
        """Strip and lowercase filter values; return None for empty strings."""
        if value is None:
            return None
        cleaned = value.strip().lower()
        return cleaned if cleaned else None


# ── Response schemas ──────────────────────────────────────────────────────────

class IntentResponse(BaseModel):
    """
    Returned after the NLP layer processes the user's message.
    confidence is a float between 0.0 (no confidence) and 1.0 (certain).

    Example:
        {"message": "I need help finding a job", "intent": "career", "confidence": 0.92}
    """
    message: str = Field(..., description="The original user message")
    intent: str = Field(..., description="Detected intent, e.g. 'career', 'health', 'legal'")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0")

    @field_validator("confidence")
    @classmethod
    def confidence_must_be_valid(cls, value: float) -> float:
        """Confidence must be a probability — between 0 and 1 inclusive."""
        if not (0.0 <= value <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return value


class RecommendationItem(BaseModel):
    """
    A single recommended resource in the /recommend response.

    Core fields map directly from a SupportResource database row.
    The source metadata fields (source, source_type, is_live, url) are
    populated when a result comes from an external data source via the
    API client layer; they are omitted (None) for pure database results
    so existing callers are unaffected.
    """
    id: int = Field(..., description="Database row ID")
    name: str = Field(..., description="Name of the resource or organisation")
    category: str = Field(..., description="Resource category")
    description: Optional[str] = Field(default=None, description="What this resource offers")
    location: Optional[str] = Field(default=None, description="Address or area in Pune")
    contact: Optional[str] = Field(default=None, description="Phone, email, or website")
    language: Optional[str] = Field(default=None, description="Language of the resource")
    score: Optional[float] = Field(default=None, description="Transparent ranking score, not a probability")
    reason: Optional[str] = Field(default=None, description="Short explanation for the recommendation")

    # ── Common resource format fields (populated for external-API results) ────
    url: Optional[str] = Field(default=None, description="Direct URL to the resource")
    source: Optional[str] = Field(default=None, description="Name of the data source")
    source_type: Optional[str] = Field(
        default=None,
        description="Origin of this record: 'api', 'official_data', or 'database'",
    )
    last_updated: Optional[str] = Field(default=None, description="ISO date the record was last refreshed")
    is_live: Optional[bool] = Field(
        default=None,
        description="True when the record came from a live external API call; "
                    "False (or absent) for verified database records",
    )


class RecommendationAPIResponse(BaseModel):
    """
    Full response returned by POST /recommend.
    Contains the original message, detected intent, confidence,
    and a list of matching support resources.

    Example:
        {
            "message": "I need help finding a job",
            "intent": "employment",
            "confidence": 0.06,
            "recommendations": [
                {
                    "id": 1,
                    "name": "Pune Women Skill Centre",
                    "category": "Employment",
                    "description": "Free skill development programmes.",
                    "location": "Shivajinagar, Pune",
                    "contact": "+91-20-12345678",
                    "language": "en"
                }
            ]
        }
    """
    message: str
    intent: str
    confidence: float
    match_score: float = Field(default=0.0, description="Top ranking score, not a probability")
    recommendations: list[RecommendationItem]


class ConversationTurn(BaseModel):
    """One turn in the conversation history sent from the frontend."""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")


class ChatRequest(BaseModel):
    """
    Request body for POST /api/chat.
    Supports follow-up queries by carrying structured conversation state.
    """
    message: str = Field(..., description="The current user message")
    category: Optional[str] = Field(default=None, description="Selected domain/category key")
    language: Optional[str] = Field(default=None, description="Language code")
    preferences: Optional[Dict[str, Any]] = Field(default=None, description="Accumulated preference answers")
    conversation_state: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured state carried between turns: intent, filters, keywords"
    )
    is_followup: bool = Field(default=False, description="True when this amends a previous query")

    @field_validator("message")
    @classmethod
    def chat_message_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty")
        return value.strip()


class ErrorResponse(BaseModel):
    """
    Returned when the API encounters an error.

    Example:
        {"error": "validation_error", "message": "message must not be empty or blank"}
    """
    error: str = Field(..., description="Short error code, e.g. 'validation_error'")
    message: str = Field(..., description="Human-readable description of what went wrong")
