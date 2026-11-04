# SakhiPune AI resource provenance audit

**Audit date:** 2026-10-24  
**Scope:** `backend/app/data/resources.csv` and official-source URL checks. Audit/reporting only; no application, CSV, database or Neon changes were made.

## Result

The resource file contains **46 data rows**, with columns:

`name, category, description, location, contact, language, keywords, experience_level, work_mode, employment_type`

There is no resource ID column and no dedicated URL, source, evidence, verification-date or verification-status column. For this report, `CSV-001` through `CSV-046` are identifiers assigned by current row order; they are not IDs stored in the source file. The report’s existing URL field is populated only when the resource’s `contact` value is an HTTP(S) URL.

| Verification status | Records |
|---|---:|
| Verified | 0 |
| Partially verified | 20 |
| Unverified | 17 |
| Incorrect | 2 |
| Inaccessible | 7 |
| **Total** | **46** |

“Partially verified” means an official source supported some material part of the resource, not necessarily every claim, eligibility rule or contact detail. “Inaccessible” denotes an existing record URL that could not be retrieved during this audit; it does not prove that the service itself is unavailable. “Incorrect” is used where the record’s link/claim combination is materially misleading, such as a non-government Ujjwala domain or the unrelated/unsupported education-policy link.

## Data integrity issue

The CSV header has 10 fields, but Python’s standard CSV reader parses the 46 data rows as having **16–21 fields each**. The keywords appear as unquoted comma-separated tokens inside a comma-delimited file. The existing `csv.DictReader` loader therefore assigns only the first token to `keywords` and spills later tokens into an extra `None` field; on rows with structured filters, keyword tokens can also be misassigned to `experience_level`, `work_mode` and `employment_type`. The source data must not be assumed to load as its apparent columns currently suggest.

This was detected without modifying or normalizing the source file. It is an important deployment/data-loading blocker: do not run the loader against production until the CSV format and field mapping are reviewed and tested on a safe copy/staging database.

## Source checks

- **21 distinct HTTP(S) URLs** were present in the CSV’s contact field and were attempted.
- **15** returned page content; **6** failed retrieval (DNS/transport failure or HTTP 403). A successful fetch only establishes that content was returned, not that the resource’s claims are true.
- Nine additional candidate URLs/pages were checked to locate official alternatives or relevant programme information. Examples include the official PMUY portal, official PMMVY portal, WCD scheme landing page, NCS and candidate helpline/legal pages. Some candidates were inaccessible; none were treated as proof beyond the content actually returned.
- Examples of useful primary evidence retrieved: Pune District’s official Yuva Karya and Ladki Bahin pages; the Maharashtra State Legal Services Authority page; the WCD and MahaDBT portals; and the TISS iCALL page. The iCALL page identifies TISS, its free telephone/email counselling, phone number and published operating hours. Pune District’s Yuva Karya page specifies online Mahaswayam registration, which conflicts with the CSV’s “apply through District Skill Development Office” wording.
- `pmujjwalayojana.com` is not the official PMUY government domain. The official PMUY portal checked was `https://pmuy.gov.in`; the page retrieved did not substantiate the CSV’s BPL-only/free-connection summary.
- PMMVY’s CSV URL did not resolve. The separate official portal `https://pmmvy.wcd.gov.in` identified Ministry/NIC ownership, but the retrieved page did not support detailed benefit or eligibility claims.

The record-by-record evidence, source organization, claims assessed and recommended action are in [resource_verification_report.csv](./resource_verification_report.csv). Records with no official source retrieved remain unverified; no unsupported URL, source or evidence was invented.

## Duplicates and potentially misleading entries

- **Bharosa Cell:** CSV-004, CSV-018, CSV-022 and CSV-044 represent the same named police cell under different categories, without evidence for the distinct service claims.
- **Sakhi One Stop Centre:** CSV-008, CSV-021 and CSV-043 overlap; the claimed Pune centre, helpline routing and five-day shelter limit were not verified.
- **Domestic-violence Protection Officer:** CSV-010 and CSV-023 overlap.
- **iCALL:** CSV-015, CSV-017 and CSV-019 describe the same provider/phone channel; the email and Marathi variants need current-source confirmation.
- **Yuva Karya Prashikshan:** CSV-025 and CSV-045 overlap; use the official term and online application guidance.
- **Ladki Bahin:** CSV-033 and CSV-041 duplicate the same scheme.
- **PMMVY:** CSV-013 and CSV-037 duplicate the same scheme.
- **Swadhar Greh:** CSV-036 and CSV-042 overlap. Confirm whether this legacy standalone scheme description is current or should refer to an updated/integrated programme before use.
- **Potential eligibility/currentness concerns:** SARTHI programme eligibility may be restricted to defined target communities; PMUY wording may be outdated/oversimplified; PMMVY’s “first child only” wording may omit current provisions; Ladki Bahin eligibility and application status may have changed since the linked 2024 district page; foreign-scholarship notices are department- and cycle-specific, and the checked portal showed a 2026–27 category as closed.

Do not delete these records solely because they remain unverified. Resolve duplicates and revise factual content only after a source-based review.

## Provenance fields and safe migration plan

The SQLAlchemy resource model currently has no provenance columns. Add nullable, additive fields in a later implementation stage, for example:

- `source_url` — URL to the page/document that supports this specific record.
- `source_name` — publisher, department, service provider or organization.
- `last_verified_at` — date/time of the last human source review; null until actually reviewed.
- `verification_status` — controlled values matching this report.
- `verification_notes` — brief claim-level caveat/evidence summary, without replacing the source itself.

Also consider a stable resource key (for example an explicit `resource_key`) that is independent of row order. Do not promote this report’s `CSV-###` values to permanent IDs without a deliberate mapping.

Recommended future migration sequence:

1. Preserve and review the existing CSV and any production records; do not truncate or reload data.
2. Correct CSV escaping/column alignment in a reviewed copy and add explicit provenance columns; verify all parsed rows have the same field count as the header.
3. Add the provenance columns as nullable fields, using a migration that does not rewrite or delete existing records.
4. Backfill only source information supported by record-level evidence. Leave `last_verified_at` null and status `Unverified` when no actual verification occurred.
5. Test the loader and migration against a disposable/staging database; verify row counts, duplicate handling and field mappings before any production operation.

## Limitations and next action

This is a point-in-time audit, not a guarantee of service availability or legal/medical advice. Some official sites were unreachable, some pages were general landing pages, and the CSV itself does not identify a source for most contact-only records. Phone numbers, addresses, eligibility, availability, service hours, benefit amounts and current enrollment were not considered verified unless the retrieved official source directly supported them.

**Recommended first action:** resolve the CSV field-alignment problem on a copy and establish a source for each existing record before loading or presenting the dataset as verified. Keep the current user-edited CSV and working tree unchanged until that review is approved.
