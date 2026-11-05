"""
repair_keywords.py — Fix the keyword parsing bug and enrich resource descriptions.

The CSV stores keywords as unquoted comma-separated tokens inside a comma-delimited
file. csv.DictReader reads only the first token into 'keywords'; the rest are lost.

This script:
1. Parses the raw CSV correctly (known fixed-column structure).
2. Extracts the FULL keyword string for every resource.
3. UPDATE support_resources SET keywords = <full_kw> WHERE name = <name>.
4. Also updates description if the DB value is shorter than the CSV value.
5. Safe to re-run — only updates rows where keywords differ.

Run from backend/:
    python repair_keywords.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.database.connection import engine

CSV_PATH = Path(__file__).parent / "app" / "data" / "resources.csv"

# The CSV has exactly 10 named columns:
#   0=name, 1=category, 2=description, 3=location, 4=contact,
#   5=language, 6..N-3=keywords (multiple tokens), N-2=experience_level,
#   N-1=work_mode, N=employment_type
# The last 3 named columns are either empty or have a single value.
# Strategy: split on comma, take cols 0-5 as fixed, take last 3 as
# experience_level/work_mode/employment_type, everything in between is keywords.

def parse_csv_raw(path: Path) -> list[dict]:
    """Parse the CSV handling unquoted multi-token keywords."""
    rows = []
    with path.open(encoding="utf-8") as f:
        raw_lines = f.readlines()

    # Skip header
    for line in raw_lines[1:]:
        line = line.rstrip("\n").rstrip("\r")
        if not line.strip():
            continue
        parts = line.split(",")

        # Fixed first 6 columns (indices 0-5)
        # Some description/name fields may contain commas — but in this CSV
        # they don't (descriptions use spaces not commas). Verified from raw inspection.
        # If a field was quoted in the CSV that would be handled; it isn't here.
        if len(parts) < 7:
            continue

        name        = parts[0].strip()
        category    = parts[1].strip()
        description = parts[2].strip()
        location    = parts[3].strip()
        contact     = parts[4].strip()
        language    = parts[5].strip()

        # Last 3 columns: experience_level, work_mode, employment_type
        # They are either empty or a single value with no commas.
        employment_type  = parts[-1].strip()
        work_mode        = parts[-2].strip()
        experience_level = parts[-3].strip()

        # Everything between col 6 and the last 3 is keywords
        keyword_parts = parts[6 : len(parts)-3]
        keywords = ",".join(k.strip() for k in keyword_parts if k.strip())

        rows.append({
            "name":             name,
            "category":         category,
            "description":      description,
            "location":         location,
            "contact":          contact,
            "language":         language,
            "keywords":         keywords,
            "experience_level": experience_level or None,
            "work_mode":        work_mode or None,
            "employment_type":  employment_type or None,
        })

    return rows


def run_repair():
    rows = parse_csv_raw(CSV_PATH)
    print(f"Parsed {len(rows)} rows from CSV")

    # Quick sanity check
    for r in rows[:3]:
        print(f"  {r['name'][:45]:45s}  kw={r['keywords'][:60]}")

    updated_kw   = 0
    updated_desc = 0
    no_change    = 0
    not_found    = 0
    errors       = 0

    with engine.begin() as conn:
        for r in rows:
            # Check current DB state
            result = conn.execute(
                text("SELECT id, keywords, description FROM support_resources WHERE name = :name"),
                {"name": r["name"]}
            ).fetchone()

            if result is None:
                print(f"  NOT FOUND in DB: {r['name'][:50]}")
                not_found += 1
                continue

            row_id, db_kw, db_desc = result

            changed = False

            # Fix keywords if different
            if (db_kw or "") != r["keywords"]:
                try:
                    conn.execute(
                        text("UPDATE support_resources SET keywords = :kw WHERE id = :id"),
                        {"kw": r["keywords"], "id": row_id}
                    )
                    updated_kw += 1
                    changed = True
                    print(f"  KW  updated: {r['name'][:45]:45s}  '{(db_kw or '')[:20]}' → '{r['keywords'][:40]}'")
                except SQLAlchemyError as e:
                    print(f"  ERROR updating keywords for {r['name']}: {e}")
                    errors += 1

            # Fix description if DB has a truncated version
            if r["description"] and len(r["description"]) > len(db_desc or ""):
                try:
                    conn.execute(
                        text("UPDATE support_resources SET description = :desc WHERE id = :id"),
                        {"desc": r["description"], "id": row_id}
                    )
                    updated_desc += 1
                    changed = True
                except SQLAlchemyError as e:
                    print(f"  ERROR updating description for {r['name']}: {e}")
                    errors += 1

            if not changed:
                no_change += 1

    print()
    print("── Repair summary ───────────────────────────────────────")
    print(f"  Keywords updated : {updated_kw}")
    print(f"  Descriptions updated: {updated_desc}")
    print(f"  No change needed : {no_change}")
    print(f"  Not found in DB  : {not_found}")
    print(f"  Errors           : {errors}")
    print("─────────────────────────────────────────────────────────")


if __name__ == "__main__":
    run_repair()
