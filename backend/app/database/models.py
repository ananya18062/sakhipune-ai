# models.py — SQLAlchemy ORM model for support resources
#
# Defines the `support_resources` table.
# Tables are created at app startup via Base.metadata.create_all() in main.py.

from sqlalchemy import Column, Integer, String, Text

from app.database.connection import Base

# ── Controlled vocabulary for structured filter columns ───────────────────────
# experience_level values (NULL = unknown / not applicable)
EXPERIENCE_LEVELS = {
    "fresher",          # no experience required
    "less_than_1",      # < 1 year
    "1_2_years",        # 1–2 years
    "3_5_years",        # 3–5 years
    "6_10_years",       # 6–10 years
    "more_than_10",     # > 10 years
    "any",              # any level accepted
}

# work_mode values (NULL = unknown)
WORK_MODES = {"remote", "hybrid", "on_site"}

# employment_type values (NULL = unknown / not applicable)
EMPLOYMENT_TYPES = {"full_time", "part_time", "contract", "apprenticeship", "self_employment"}


class SupportResource(Base):
    """
    Represents a single women's support resource in Pune.

    Examples of what rows will contain:
        - Emergency helplines
        - Legal aid centres
        - Healthcare facilities
        - Counselling services
        - Employment and skill-training programmes
        - Education support
        - Government schemes
        - Shelters
        - Financial support
        - Domestic violence support
    """

    __tablename__ = "support_resources"

    # Primary key — auto-incremented by PostgreSQL
    id = Column(Integer, primary_key=True, index=True)

    # Name of the resource or organisation
    name = Column(String(255), nullable=False)

    # Category, e.g. "legal", "health", "employment", "shelter"
    category = Column(String(100), nullable=False)

    # Full description of what the resource offers
    description = Column(Text, nullable=True)

    # Physical address or area in Pune
    location = Column(String(255), nullable=True)

    # Phone number, email, or website
    contact = Column(String(255), nullable=True)

    # Language the resource is available in, e.g. "en", "mr", "hi"
    language = Column(String(50), nullable=True, default="en")

    # Comma-separated keywords for matching, e.g. "job,career,skill"
    keywords = Column(Text, nullable=True)

    # ── Direct action links ───────────────────────────────────────────────────
    # apply_url: the direct application, registration, or service-access page.
    # This is intentionally separate from contact — contact may be a phone/email
    # while apply_url is always an https:// link to the action page.
    # NULL means no verified application link exists for this resource.
    apply_url = Column(String(512), nullable=True)

    # action_label: the button text for apply_url, e.g. "Apply Now", "Register Here".
    # NULL falls back to a category-derived default in the API layer.
    action_label = Column(String(80), nullable=True)

    # ── Structured filter metadata ────────────────────────────────────────────
    # These columns enable accurate filtering without keyword guessing.
    # NULL means the information is genuinely unknown — never default to a value.

    # Experience level required, e.g. "fresher", "1_2_years", "any"
    # See EXPERIENCE_LEVELS for the full vocabulary.
    experience_level = Column(String(50), nullable=True)

    # Work mode of the opportunity: "remote", "hybrid", "on_site"
    # NULL = unknown — do NOT include in remote-only results.
    work_mode = Column(String(20), nullable=True)

    # Employment type: "full_time", "part_time", "contract", "apprenticeship", "self_employment"
    employment_type = Column(String(30), nullable=True)

    def __repr__(self) -> str:
        return f"<SupportResource id={self.id} name='{self.name}' category='{self.category}'>"
