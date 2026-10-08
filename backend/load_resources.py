"""load_resources.py — Load verified Pune support resources from CSV into PostgreSQL.

Usage (from the backend/ directory with the virtual environment active):
    python load_resources.py

Behaviour:
  - Reads app/data/resources.csv
  - Creates the support_resources table if it does not exist
  - Skips rows whose (name, category) pair already exists in the database
  - Inserts only new rows — safe to run multiple times without creating duplicates
  - Prints a clear summary of inserted / skipped / failed counts
  - Exits with code 1 if the database is unreachable so CI pipelines can detect failure
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Make sure the app package is importable when the script is run from backend/
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.connection import Base, SessionLocal, engine
from app.database.models import SupportResource

CSV_PATH = Path(__file__).parent / "app" / "data" / "resources.csv"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_csv(path: Path) -> list[dict]:
    """Read the CSV and return a list of row dicts. Exits on file-not-found."""
    if not path.exists():
        print(f"ERROR: CSV not found at {path}")
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"INFO:  Read {len(rows)} rows from {path.name}")
    return rows


def _existing_keys(db: Session) -> set[tuple[str, str]]:
    """Return a set of (name_lower, category_lower) tuples already in the DB."""
    results = db.query(SupportResource.name, SupportResource.category).all()
    return {(name.lower(), cat.lower()) for name, cat in results}


def _row_to_resource(row: dict) -> SupportResource | None:
    """
    Convert a CSV row dict to a SupportResource ORM object.
    Returns None and prints a warning if required fields are missing.
    """
    name = row.get("name", "").strip()
    category = row.get("category", "").strip()
    if not name or not category:
        print(f"WARNING: Skipping row with missing name or category: {row}")
        return None

    return SupportResource(
        name=name,
        category=category,
        description=row.get("description", "").strip() or None,
        location=row.get("location", "").strip() or None,
        contact=row.get("contact", "").strip() or None,
        language=row.get("language", "").strip() or "en",
        keywords=row.get("keywords", "").strip() or None,
    )


# ── Main loader ───────────────────────────────────────────────────────────────

def load_resources() -> None:
    """Full load pipeline: ensure table → read CSV → skip dupes → insert new."""

    # 1. Ensure table exists
    try:
        Base.metadata.create_all(bind=engine)
        print("INFO:  Database table confirmed / created.")
    except SQLAlchemyError as exc:
        print(f"ERROR: Cannot connect to database — {exc.__class__.__name__}")
        print("       Check DATABASE_URL in backend/.env and ensure PostgreSQL is running.")
        sys.exit(1)

    # 2. Read CSV
    rows = _read_csv(CSV_PATH)

    # 3. Open session and load
    db: Session = SessionLocal()
    inserted = 0
    skipped = 0
    failed = 0

    try:
        existing = _existing_keys(db)
        print(f"INFO:  {len(existing)} existing record(s) in database.")

        for row in rows:
            resource = _row_to_resource(row)
            if resource is None:
                failed += 1
                continue

            key = (resource.name.lower(), resource.category.lower())
            if key in existing:
                skipped += 1
                continue

            try:
                db.add(resource)
                db.flush()          # catch constraint errors per-row
                existing.add(key)   # prevent in-session dupes from the same CSV
                inserted += 1
            except SQLAlchemyError as exc:
                db.rollback()
                print(f"WARNING: Failed to insert '{resource.name}' — {exc.__class__.__name__}")
                failed += 1

        db.commit()

    except SQLAlchemyError as exc:
        db.rollback()
        print(f"ERROR: Database session failed — {exc.__class__.__name__}")
        sys.exit(1)
    finally:
        db.close()

    # 4. Summary
    print()
    print("── Load summary ─────────────────────────────────")
    print(f"  Rows in CSV   : {len(rows)}")
    print(f"  Inserted      : {inserted}")
    print(f"  Skipped (dupe): {skipped}")
    print(f"  Failed        : {failed}")
    print("─────────────────────────────────────────────────")

    if failed:
        print(f"WARNING: {failed} row(s) were not loaded. Check warnings above.")
    else:
        print("INFO:  All rows processed successfully.")


if __name__ == "__main__":
    load_resources()
