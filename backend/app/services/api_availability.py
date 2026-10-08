"""api_availability.py — Single source of truth for external API status.

This module documents the verified availability status of every external
data source for SakhiPune AI as of September 2026.

It is used by:
  • GET /api/availability  (operator endpoint — never exposed to users)
  • Every category service, to document why its API URL is empty by default

Rules
─────
  • Never add an endpoint here without verifying it exists and is accessible
    without institutional/private credentials.
  • Update the status and last_verified date whenever a source is checked.
  • If an API becomes available, add its URL to config.py and .env.example,
    then update this file's status to "available".

Status values
─────────────
  "unavailable"   — Verified to exist but requires login / not open
  "web_only"      — Portal exists but no JSON API endpoint
  "available"     — Public unauthenticated JSON endpoint confirmed
  "unknown"       — Not yet verified
"""

from __future__ import annotations

from typing import Any

# ── Verified API availability (September 2026) ────────────────────────────────

AVAILABILITY: dict[str, dict[str, Any]] = {
    "education": {
        "config_key":    "EDUCATION_API_URL",
        "status":        "unavailable",
        "reason":        (
            "NSP (scholarships.gov.in) uses an XML push API requiring institutional "
            "registration. MahaDbt (mahadbt.maharashtra.gov.in) requires institutional "
            "login for all endpoints."
        ),
        "fallback":      "PostgreSQL verified data",
        "last_verified": "2026-09-12",
        "sources_checked": [
            "https://scholarships.gov.in",
            "https://mahadbt.maharashtra.gov.in",
            "https://fs.maharashtra.gov.in",
        ],
    },
    "employment": {
        "config_key":    "JOBS_API_URL",
        "status":        "unavailable",
        "reason":        (
            "NCS (ncs.gov.in) vacancy booking requires employer login. "
            "Mahaswayam (mahaswayam.gov.in) requires institutional login for vacancy data. "
            "data.gov.in requires an API key with no real-time jobs endpoint."
        ),
        "fallback":      "PostgreSQL verified data",
        "last_verified": "2026-09-12",
        "sources_checked": [
            "https://ncs.gov.in",
            "https://mahaswayam.gov.in",
            "https://data.gov.in",
        ],
    },
    "internships": {
        "config_key":    "INTERNSHIPS_API_URL",
        "status":        "unavailable",
        "reason":        (
            "No public unauthenticated internship listings API exists for "
            "Pune/Maharashtra. Government internship schemes (SARTHI, Mukhyamantri Yuva) "
            "are static scheme information, not live listings."
        ),
        "fallback":      "PostgreSQL verified data",
        "last_verified": "2026-09-12",
        "sources_checked": [
            "https://sarthi.maharashtra.gov.in",
            "https://pune.gov.in",
        ],
    },
    "healthcare": {
        "config_key":    "HEALTHCARE_API_URL",
        "status":        "web_only",
        "reason":        (
            "NHM (nhm.gov.in), PMC (pmc.gov.in) and PMMVY (pmmvy-cas.nic.in) "
            "are web portals without open JSON endpoints."
        ),
        "fallback":      "PostgreSQL verified data",
        "last_verified": "2026-09-12",
        "sources_checked": [
            "https://nhm.gov.in",
            "https://pmc.gov.in",
            "https://pmmvy-cas.nic.in",
        ],
    },
    "legal": {
        "config_key":    "LEGAL_API_URL",
        "status":        "web_only",
        "reason":        (
            "Pune DLSA (punedlsa.org) and MSLSA (legalservices.maharashtra.gov.in) "
            "are web-only portals without open JSON endpoints."
        ),
        "fallback":      "PostgreSQL verified data",
        "last_verified": "2026-09-12",
        "sources_checked": [
            "https://punedlsa.org",
            "https://legalservices.maharashtra.gov.in",
            "https://bombayhighcourt.gov.in",
        ],
    },
    "financial_support": {
        "config_key":    "FINANCIAL_API_URL",
        "status":        "web_only",
        "reason":        (
            "MAVIM (mavim.maharashtra.gov.in), Jan Dhan (pmjdy.gov.in) and "
            "NULM (pmc.gov.in) are web-only portals without open JSON endpoints."
        ),
        "fallback":      "PostgreSQL verified data",
        "last_verified": "2026-09-12",
        "sources_checked": [
            "https://mavim.maharashtra.gov.in",
            "https://pmjdy.gov.in",
            "https://ladakibahin.maharashtra.gov.in",
        ],
    },
    "shelter": {
        "config_key":    "SHELTER_API_URL",
        "status":        "web_only",
        "reason":        (
            "Swadhar Greh scheme (wcd.gov.in) and Sakhi OSC are government schemes "
            "contactable only via helpline 181. No JSON API for shelter listings exists."
        ),
        "fallback":      "PostgreSQL verified data",
        "last_verified": "2026-09-12",
        "sources_checked": [
            "https://wcd.gov.in",
            "https://spniwcd.wcd.gov.in",
        ],
    },
    "emergency": {
        "config_key":    "EMERGENCY_API_URL",
        "status":        "not_required",
        "reason":        (
            "Core emergency helplines (100, 108, 181, 1091) are static verified "
            "government numbers that do not change. No live API is needed or suitable. "
            "An API URL can be set if a supplementary real-time resource directory "
            "becomes available."
        ),
        "fallback":      "PostgreSQL verified data (static helplines)",
        "last_verified": "2026-09-12",
        "sources_checked": [
            "https://pune.gov.in/en/helpline/",
        ],
    },
    "counselling": {
        "config_key":    "COUNSELLING_API_URL",
        "status":        "web_only",
        "reason":        (
            "iCALL (icallhelpline.org / TISS) and Vandrevala Foundation provide "
            "counselling via phone/email but have no open JSON API for resource listings."
        ),
        "fallback":      "PostgreSQL verified data",
        "last_verified": "2026-09-12",
        "sources_checked": [
            "https://icallhelpline.org",
            "https://tiss.edu",
        ],
    },
    "government_scheme": {
        "config_key":    "GOVERNMENT_API_URL",
        "status":        "web_only",
        "reason":        (
            "Maharashtra WCD (womenchild.maharashtra.gov.in), WCD central (wcd.gov.in) "
            "and PMMVY (pmmvy-cas.nic.in) are web-only portals. "
            "National Scheme Portal has an authenticated API only."
        ),
        "fallback":      "PostgreSQL verified data",
        "last_verified": "2026-09-12",
        "sources_checked": [
            "https://womenchild.maharashtra.gov.in",
            "https://wcd.gov.in",
            "https://pmmvy-cas.nic.in",
            "https://pmujjwalayojana.com",
        ],
    },
}


def get_availability() -> dict[str, Any]:
    """Return the full API availability map for all categories."""
    return {
        "categories": AVAILABILITY,
        "summary": {
            "total":          len(AVAILABILITY),
            "available":      sum(1 for v in AVAILABILITY.values() if v["status"] == "available"),
            "unavailable":    sum(1 for v in AVAILABILITY.values() if v["status"] == "unavailable"),
            "web_only":       sum(1 for v in AVAILABILITY.values() if v["status"] == "web_only"),
            "not_required":   sum(1 for v in AVAILABILITY.values() if v["status"] == "not_required"),
            "fallback_active": "All categories use PostgreSQL verified data fallback",
        },
        "note": (
            "No public unauthenticated JSON API is available for any SakhiPune AI "
            "category as of September 2026. All categories serve verified PostgreSQL "
            "data with is_live=false. When an API becomes available, set the "
            "corresponding *_API_URL in .env — the service will automatically attempt "
            "a live fetch and fall back to PostgreSQL on any failure."
        ),
    }


def is_api_available(category: str) -> bool:
    """Return True only if a verified public API is configured for this category."""
    return AVAILABILITY.get(category, {}).get("status") == "available"
