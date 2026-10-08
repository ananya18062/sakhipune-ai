# config.py — Application configuration loaded from environment variables
#
# Uses pydantic-settings so every value can be overridden via a .env file
# or a real environment variable without touching this code.

from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    # Application
    APP_NAME: str = "SakhiPune AI"
    DEBUG: bool = True

    # External API transport — applies to every BaseAPIClient instance
    # Override in .env to tighten or relax per deployment environment
    EXTERNAL_API_TIMEOUT_SECONDS: float = 10.0

    # Database — must be overridden in .env with real credentials
    DATABASE_URL: str = "postgresql://username:password@localhost:5432/sakhipune"

    # Frontend origin — used for CORS in main.py
    # Both localhost and 127.0.0.1 are listed because VS Code Live Server
    # may serve on either address depending on system configuration
    FRONTEND_URL: str = "http://localhost:5500"
    FRONTEND_URL_ALT: str = "http://127.0.0.1:5500"

    # ── External API keys ─────────────────────────────────────────────────────
    # Keys are loaded exclusively from .env — never hard-coded here.
    # Leave the defaults as empty strings; the application checks for
    # a non-empty value before attempting any external call.
    #
    # Add a matching entry to .env.example (no real values) whenever a new
    # key is introduced so teammates know which variables to set locally.

    # Placeholder — replace with the correct variable name when a real
    # data-source integration is added in a later task.
    EXTERNAL_API_KEY: str = ""

    # Education / Scholarship API — leave empty until a public endpoint is available.
    # When set, education_service.py will attempt a live fetch before falling back to DB.
    EDUCATION_API_URL: str = ""

    # Jobs / Employment API — leave empty until a public endpoint is available.
    # NCS (ncs.gov.in) and Mahaswayam both require institutional login as of Sep 2026.
    # When set, jobs_service.py will attempt a live fetch before falling back to DB.
    JOBS_API_URL: str = ""

    # Internships API — leave empty until a public endpoint is available.
    # No public unauthenticated internship listings API exists for Pune/Maharashtra
    # as of September 2026.
    # When set, internship_service.py will attempt a live fetch before falling back to DB.
    INTERNSHIPS_API_URL: str = ""

    # Healthcare API — leave empty until a public endpoint is available.
    # NHM, PMC and PMMVY portals are web-only without open JSON endpoints as of Sep 2026.
    # When set, healthcare_service.py will attempt a live fetch before falling back to DB.
    HEALTHCARE_API_URL: str = ""

    # Legal Support API — leave empty until a public endpoint is available.
    # DLSA and MSLSA portals are web-only without open JSON endpoints as of Sep 2026.
    # When set, legal_service.py will attempt a live fetch before falling back to DB.
    LEGAL_API_URL: str = ""

    # Financial Support API — leave empty until a public endpoint is available.
    # MAVIM, NULM and Jan Dhan portals are web-only without open JSON endpoints as of Sep 2026.
    # When set, financial_service.py will attempt a live fetch before falling back to DB.
    FINANCIAL_API_URL: str = ""

    # Shelter API
    SHELTER_API_URL: str = ""

    # Emergency API (supplementary — core helplines are static verified numbers)
    EMERGENCY_API_URL: str = ""

    # Counselling API
    COUNSELLING_API_URL: str = ""

    # Government Schemes API
    GOVERNMENT_API_URL: str = ""

    # ── Deployment ────────────────────────────────────────────────────────────
    # Extra CORS origins for production (e.g. the Vercel frontend domain).
    # Set this in Vercel environment variables when the deployment domain is known.
    # Format: comma-separated list, e.g.  "https://sakhipune.vercel.app"
    # Leave empty during local development — localhost origins are always included.
    ALLOWED_ORIGINS: str = ""

    # Tell pydantic-settings to load from a .env file when present
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Single shared instance — import this wherever config values are needed
# Example:  from app.core.config import settings
settings = Settings()
