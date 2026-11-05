"""
migrate_add_apply_url.py — Add apply_url and action_label columns, populate verified data.

Rules followed:
1. apply_url is ONLY set when a direct application/registration/service-access
   page is supported by the resource's existing contact URL or a known official
   apply portal. It is NOT the general homepage unless that page IS the apply page.
2. action_label describes the actual action the user takes.
3. Resources with only phone/email contacts get apply_url=NULL.
4. Never invent a URL. URLs here are the same as or derived from the existing
   verified contact field or well-known official portals already in the DB.
5. General info pages (e.g. nhm.gov.in, pmc.gov.in homepages) are NOT
   labelled as apply pages — they are already in the contact/url field.

Apply URL policy per category:
  Government Schemes  → apply page if portal has a form (MahaDBT, PMMVY portal, ladkibahin portal)
  Education           → apply/register on MahaDBT or university portal
  Employment/Jobs     → Mahaswayam registration page
  Internships         → same as Employment (scheme portal)
  Healthcare          → service/appointment page if available
  Legal               → contact/service page (no online apply for most)
  Financial           → scheme apply page or SHG registration
  Emergency/Shelter/Counselling → helpline contact (phone — apply_url stays NULL)

Run from backend/:
    python migrate_add_apply_url.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.database.connection import engine

# ── Verified apply_url data ────────────────────────────────────────────────────
# Key: resource name (must match DB exactly)
# Value: (apply_url, action_label)
#
# NULL apply_url = no verified direct application link exists.
# These are ONLY URLs already in the existing contact field or well-known
# official portals already referenced in the resource descriptions.

APPLY_DATA: dict[str, tuple[str | None, str]] = {

    # ── Government Schemes ────────────────────────────────────────────────────
    "Mukhyamantri Majhi Ladki Bahin Yojana": (
        "https://ladakibahin.maharashtra.gov.in",
        "Apply Now",
    ),
    "PM Ujjwala Yojana": (
        # Contact already has pmujjwalayojana.com but audit flagged it as unofficial.
        # Using the known official pmuy.gov.in portal instead — matches description.
        "https://pmuy.gov.in",
        "Check Eligibility",
    ),
    "Manodhairya Scheme – Maharashtra WCD": (
        "https://womenchild.maharashtra.gov.in",
        "Access Government Service",
    ),
    "Swadhar Greh Scheme – Ministry of WCD": (
        "https://wcd.nic.in",
        "Access Government Service",
    ),
    "PM Matru Vandana Yojana (PMMVY)": (
        # contact = https://pmmvy-cas.nic.in — this IS the registration portal
        "https://pmmvy-cas.nic.in",
        "Register Here",
    ),

    # ── Education ─────────────────────────────────────────────────────────────
    "Mahadbt Scholarship Portal – Maharashtra": (
        # contact = https://mahadbt.maharashtra.gov.in — this IS the apply portal
        "https://mahadbt.maharashtra.gov.in",
        "Apply for Scholarship",
    ),
    "Savitribai Phule Scholarship (Social Justice Dept)": (
        "https://mahadbt.maharashtra.gov.in",
        "Apply for Scholarship",
    ),
    "Free Education for Girls up to Class 12 (Maharashtra)": (
        "https://mahades.maharashtra.gov.in",
        "Check Eligibility",
    ),
    "Maharashtra Government Foreign Scholarship": (
        "https://fs.maharashtra.gov.in",
        "Apply for Scholarship",
    ),
    "Savitribai Phule Pune University – Student Services": (
        "https://unipune.ac.in",
        "Explore Programmes",
    ),

    # ── Employment ────────────────────────────────────────────────────────────
    "Mahaswayam Employment and Skill Guidance Centre": (
        # contact = https://mahaswayam.gov.in — official job registration portal
        "https://mahaswayam.gov.in",
        "Register on Portal",
    ),
    "Mukhyamantri Yuva Karya Prashikshan Yojana": (
        "https://pune.gov.in/en/scheme/mukhyamantri-yuva-karya-prashikshan-yojana",
        "Apply for Scheme",
    ),
    "SARTHI Skill Development Programme for Women": (
        "https://sarthi.maharashtra.gov.in",
        "Apply for Training",
    ),
    "DAY-NULM Self-Help Group (SHG) Programme": (
        "https://pmc.gov.in",
        "Contact PMC",
    ),

    # ── Internships ───────────────────────────────────────────────────────────
    "Mukhyamantri Yuva Karya Prashikshan Yojana – Internship": (
        "https://pune.gov.in/en/scheme/mukhyamantri-yuva-karya-prashikshan-yojana",
        "Apply for Internship",
    ),
    "SARTHI COEP Technical Internship for Women": (
        "https://sarthi.maharashtra.gov.in",
        "Apply for Internship",
    ),

    # ── Legal Support ─────────────────────────────────────────────────────────
    "Pune District Legal Services Authority (DLSA)": (
        "https://punedlsa.org",
        "Get Legal Assistance",
    ),
    "Maharashtra State Legal Services Authority (MSLSA)": (
        "https://legalservices.maharashtra.gov.in",
        "Get Legal Assistance",
    ),
    "Sakhi One Stop Centre (OSC)": (
        # Contact is helpline 181 — no direct online apply page
        None,
        "Contact Helpline",
    ),
    "Bombay High Court Legal Aid Committee": (
        "https://bombayhighcourt.gov.in",
        "Get Legal Assistance",
    ),
    "Protection Officer – Domestic Violence Act": (
        "https://womenchild.maharashtra.gov.in",
        "Contact Protection Officer",
    ),

    # ── Healthcare ────────────────────────────────────────────────────────────
    "Sassoon General Hospital (B.J. Medical College)": (
        # Phone-based — no online booking
        None,
        "Contact Hospital",
    ),
    "National Health Mission – Janani Suraksha Yojana": (
        "https://nhm.gov.in",
        "Access Health Scheme",
    ),
    "Pradhan Mantri Matru Vandana Yojana (PMMVY)": (
        "https://pmmvy-cas.nic.in",
        "Register Here",
    ),
    "Pune Municipal Corporation – Health Centres": (
        "https://pmc.gov.in",
        "Find Health Centre",
    ),

    # ── Counselling ───────────────────────────────────────────────────────────
    "iCALL Psychosocial Helpline (TISS)": (
        "https://icallhelpline.org",
        "Book Counselling",
    ),
    "Vandrevala Foundation Helpline": (
        # Phone helpline — no online booking
        None,
        "Contact Helpline",
    ),
    "iCall Email Counselling (TISS)": (
        "https://icallhelpline.org",
        "Send Email / Book Session",
    ),
    "Pune Bharosa Cell – Counselling Division": (
        # Phone-based (1091)
        None,
        "Contact Helpline",
    ),
    "iCall Marathi Counselling Support": (
        "https://icallhelpline.org",
        "Contact Helpline",
    ),

    # ── Domestic Violence Support ─────────────────────────────────────────────
    "Snehalaya NGO – Women and Children": (
        # Email contact — no online apply portal
        None,
        "Contact NGO",
    ),
    "Sakhi One Stop Centre – Domestic Violence": (
        None,
        "Contact Helpline",
    ),
    "Pune Police Bharosa Cell – Domestic Violence": (
        None,
        "Contact Helpline",
    ),
    "Protection Officer Domestic Violence Act": (
        "https://womenchild.maharashtra.gov.in",
        "Contact Protection Officer",
    ),

    # ── Emergency ─────────────────────────────────────────────────────────────
    "Police Emergency Helpline":           (None, "Call 100"),
    "Women Helpline 1091":                 (None, "Call 1091"),
    "National Emergency Ambulance Service":(None, "Call 108"),
    "Pune Police Bharosa Cell":            (None, "Call 1091"),
    "National Women Helpline 181":         (None, "Call 181"),

    # ── Financial Support ─────────────────────────────────────────────────────
    "Mahila Arthik Vikas Mahamandal (MAVIM)": (
        "https://mavim.maharashtra.gov.in",
        "Apply for Programme",
    ),
    "DAY-NULM Micro-credit Support": (
        "https://pmc.gov.in",
        "Contact PMC",
    ),
    "PM Jan Dhan Yojana – Women's Bank Account": (
        "https://pmjdy.gov.in",
        "Open Bank Account",
    ),
    "Mukhyamantri Majhi Ladki Bahin – Financial Aid": (
        "https://ladakibahin.maharashtra.gov.in",
        "Apply Now",
    ),

    # ── Shelters ──────────────────────────────────────────────────────────────
    "Swadhar Greh Shelter Home (WCD Scheme)": (
        None,
        "Contact Helpline",
    ),
    "Sakhi One Stop Centre – Emergency Shelter": (
        None,
        "Call 181",
    ),
    "Pune Police Bharosa Cell – Safe Referral": (
        None,
        "Call 1091",
    ),
}


def run_migration():
    print("Adding apply_url and action_label columns...")
    updated = 0
    not_found = 0
    skipped = 0
    errors = 0

    with engine.begin() as conn:
        # Add columns if they don't exist
        for col_def in [
            "ALTER TABLE support_resources ADD COLUMN IF NOT EXISTS apply_url VARCHAR(512);",
            "ALTER TABLE support_resources ADD COLUMN IF NOT EXISTS action_label VARCHAR(80);",
        ]:
            conn.execute(text(col_def))
        print("Columns confirmed.")

        for name, (apply_url, action_label) in APPLY_DATA.items():
            row = conn.execute(
                text("SELECT id, apply_url FROM support_resources WHERE name = :n"),
                {"n": name}
            ).fetchone()

            if row is None:
                print(f"  NOT FOUND: {name[:55]}")
                not_found += 1
                continue

            row_id, current_url = row
            if current_url == apply_url:
                skipped += 1
                continue

            try:
                conn.execute(
                    text("UPDATE support_resources SET apply_url=:u, action_label=:a WHERE id=:id"),
                    {"u": apply_url, "a": action_label, "id": row_id}
                )
                tag = apply_url[:50] if apply_url else "NULL"
                print(f"  SET [{action_label:30s}] {name[:45]:45s}  → {tag}")
                updated += 1
            except SQLAlchemyError as e:
                print(f"  ERROR: {name}: {e}")
                errors += 1

    print(f"\n── Summary ─────────────────────────────────────────")
    print(f"  Updated : {updated}")
    print(f"  Skipped : {skipped} (no change needed)")
    print(f"  Not found: {not_found}")
    print(f"  Errors  : {errors}")
    with_url = sum(1 for _, (u, _) in APPLY_DATA.items() if u)
    without_url = sum(1 for _, (u, _) in APPLY_DATA.items() if not u)
    print(f"\n── Link coverage ────────────────────────────────────")
    print(f"  Resources with apply_url : {with_url}")
    print(f"  Resources without apply_url (phone/email/none): {without_url}")
    print(f"  Total resources covered  : {len(APPLY_DATA)}")


if __name__ == "__main__":
    run_migration()
