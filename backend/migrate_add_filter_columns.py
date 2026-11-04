"""migrate_add_filter_columns.py — Safe schema migration for SakhiPune AI.

Adds three structured filter columns to support_resources:
  - experience_level  VARCHAR(50)   NULL
  - work_mode         VARCHAR(20)   NULL
  - employment_type   VARCHAR(30)   NULL

Then populates known values for Employment and Internship resources.

Usage (from the backend/ directory with the virtual environment active):
    python migrate_add_filter_columns.py

Safe to run multiple times — uses IF NOT EXISTS and skips already-set rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the app package importable when run from backend/
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database.connection import engine


def run_migration() -> None:
    """Apply the filter-column migration."""

    # ── Step 1: Add columns (idempotent — PostgreSQL IF NOT EXISTS) ───────────
    add_columns_sql = [
        """
        ALTER TABLE support_resources
        ADD COLUMN IF NOT EXISTS experience_level VARCHAR(50);
        """,
        """
        ALTER TABLE support_resources
        ADD COLUMN IF NOT EXISTS work_mode VARCHAR(20);
        """,
        """
        ALTER TABLE support_resources
        ADD COLUMN IF NOT EXISTS employment_type VARCHAR(30);
        """,
    ]

    # ── Step 2: Populate known filter metadata ────────────────────────────────
    # These UPDATE statements only set values where we have reliable information.
    # Rows not listed here keep NULL (= unknown), which is the correct behaviour.
    #
    # Experience level vocabulary:
    #   fresher, less_than_1, 1_2_years, 3_5_years, 6_10_years, more_than_10, any
    #
    # Work mode vocabulary:
    #   remote, hybrid, on_site
    #
    # Employment type vocabulary:
    #   full_time, part_time, contract, apprenticeship, self_employment

    populate_sql = [
        # ── Employment resources ─────────────────────────────────────────────
        # Mahaswayam: general career guidance centre, accepts all experience levels
        """
        UPDATE support_resources
        SET experience_level = 'any',
            work_mode        = 'on_site',
            employment_type  = 'full_time'
        WHERE name ILIKE '%Mahaswayam Employment%'
          AND category ILIKE 'Employment'
          AND experience_level IS NULL;
        """,
        # Mukhyamantri Yuva Karya: paid apprenticeship for youth — fresher-friendly
        """
        UPDATE support_resources
        SET experience_level = 'fresher',
            work_mode        = 'on_site',
            employment_type  = 'apprenticeship'
        WHERE name ILIKE '%Mukhyamantri Yuva Karya%'
          AND category ILIKE 'Employment'
          AND experience_level IS NULL;
        """,
        # SARTHI Skill Development: free training for women — freshers and beginners
        """
        UPDATE support_resources
        SET experience_level = 'fresher',
            work_mode        = 'on_site',
            employment_type  = 'full_time'
        WHERE name ILIKE '%SARTHI Skill Development%'
          AND category ILIKE 'Employment'
          AND experience_level IS NULL;
        """,
        # DAY-NULM SHG: self-help / micro-business, no experience required
        """
        UPDATE support_resources
        SET experience_level = 'fresher',
            work_mode        = 'on_site',
            employment_type  = 'self_employment'
        WHERE name ILIKE '%DAY-NULM%'
          AND category ILIKE 'Employment'
          AND experience_level IS NULL;
        """,

        # ── Internship resources ─────────────────────────────────────────────
        # Mukhyamantri Yuva Karya – Internship (on-site apprenticeship)
        """
        UPDATE support_resources
        SET experience_level = 'fresher',
            work_mode        = 'on_site',
            employment_type  = 'apprenticeship'
        WHERE name ILIKE '%Mukhyamantri Yuva Karya%'
          AND category ILIKE 'Internships'
          AND experience_level IS NULL;
        """,
        # SARTHI COEP Technical Internship (on-site, technical, women)
        """
        UPDATE support_resources
        SET experience_level = 'fresher',
            work_mode        = 'on_site',
            employment_type  = 'apprenticeship'
        WHERE name ILIKE '%SARTHI COEP%'
          AND category ILIKE 'Internships'
          AND experience_level IS NULL;
        """,
    ]

    try:
        with engine.begin() as conn:
            print("── Step 1: Adding columns ────────────────────────────────")
            for sql in add_columns_sql:
                conn.execute(text(sql))
                print(f"  OK: {sql.strip().split()[3]}")  # prints column name

            print("\n── Step 2: Populating filter metadata ────────────────────")
            for sql in populate_sql:
                result = conn.execute(text(sql))
                print(f"  Rows updated: {result.rowcount}")

        print("\n── Migration complete ─────────────────────────────────────")
        print("  experience_level, work_mode, employment_type columns ready.")

    except SQLAlchemyError as exc:
        print(f"\nERROR: Migration failed — {exc.__class__.__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
