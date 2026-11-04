# Resource CSV alignment repair diagnostics

**Scope:** offline structural diagnosis and a non-production corrected candidate only. No application code, original CSV, database, Neon records, or deployment configuration was changed. No database connection was opened.

## Source and schema

- Original file: `backend/app/data/resources.csv`
- Header has 10 columns: `name, category, description, location, contact, language, keywords, experience_level, work_mode, employment_type`
- Data rows: 46 (source record rows 2–47, counting the header as row 1)
- The original file’s SHA-256 before and after candidate generation is `24b6d4be6501e2b86c0491c755d58b4d43386fdb011342c305d6261341d8ecfd`.

The SQLAlchemy model is `SupportResource` in `backend/app/database/models.py`. Its fields, storage types and observed/declared constraints are:

| CSV column | SQLAlchemy field | Type / constraints | Consumer |
|---|---|---|---|
| `name` | `name` | `String(255)`, required | Display and TF-IDF resource text |
| `category` | `category` | `String(100)`, required; model does not enforce an enum | Intent/category routing, display and TF-IDF text |
| `description` | `description` | Nullable `Text` | Display and TF-IDF resource text |
| `location` | `location` | Nullable `String(255)` | Recommendation location scoring and display |
| `contact` | `contact` | Nullable `String(255)` | Display/contact normalization |
| `language` | `language` | Nullable `String(50)`, ORM default `en` | Recommendation language scoring |
| `keywords` | `keywords` | Nullable `Text`; documented as comma-separated | TF-IDF resource text |
| `experience_level` | `experience_level` | Nullable `String(50)`; `{fresher, less_than_1, 1_2_years, 3_5_years, 6_10_years, more_than_10, any}` | Employment/internship filters |
| `work_mode` | `work_mode` | Nullable `String(20)`; `{remote, hybrid, on_site}` | Employment/internship filters |
| `employment_type` | `employment_type` | Nullable `String(30)`; `{full_time, part_time, contract, apprenticeship, self_employment}` | Employment filters |

The CSV itself uses 11 observed category labels; `SupportResource.category` is a string, not a database enum. The candidate preserves those labels exactly. The Pydantic request schema defines filters sent by users, not a replacement resource-data schema.

## Root cause and row diagnosis

Python’s standard `csv.reader` parsed the source as follows:

| Parsed cells in source row | Number of rows |
|---:|---:|
| 16 | 1 |
| 17 | 2 |
| 18 | 8 |
| 19 | 23 |
| 20 | 7 |
| 21 | 5 |

**All 46 records have more than 10 parsed cells.** The first six parsed cells consistently align with the resource model’s fixed fields: name, category, description, location, contact and language. The category matches an observed source category and language is `en` or `mr` in every row. No extra cells were found before those anchors.

The surplus fields are keyword spillover plus three trailing filter cells—not arbitrary text to append blindly to keywords:

- The source model explicitly defines `keywords` as comma-separated text. The source rows write each keyword as a separate unquoted CSV cell, so commas split that one logical field into multiple parsed cells.
- The final three cells of every record can be isolated as `experience_level`, `work_mode` and `employment_type`: all 46 suffixes are either blank or match the exact controlled vocabularies declared in the model.
- Six rows have populated, valid filter suffixes: source rows **25–28, 46 and 47**. The other **40** have empty suffixes, preserved as empty/unknown filter values.
- Example of the old `DictReader` shift: for the Police Emergency Helpline, parsed keyword cells begin `emergency, police, danger, help, …`. With positional mapping against the 10-column header, the first keyword tokens can incorrectly occupy `keywords`, `experience_level`, `work_mode` and subsequent fields, while remaining cells land in `None`. In contrast, the Mahaswayam record’s actual tail is `any, on_site, full_time`; these filter values are not keywords and must be restored to their dedicated columns.
- Repeated values and similarly named resources are preserved. This stage does not merge records or evaluate their factual correctness.

The original does not contain quoted embedded commas/newlines inside the first six fields. Those fields were retained byte-for-value as parsed; keyword cells were rejoined in their original order with commas into the single `keywords` field. The candidate uses Python’s `csv.DictWriter` to quote and escape fields correctly.

## Repair result and comparison

- **Automatically repaired:** 46 records.
- **Ambiguous:** 0 records.
- **Omitted from candidate:** 0 records.
- **Missing or silently rewritten field values:** none identified in the field-by-field comparison.
- **Combined fields:** the keyword cells for each row are intentionally rejoined into the model’s single comma-separated `keywords` value. The final three filter cells are kept separate and not combined with keywords.
- The candidate retains the original 10-column header, resource names, categories, descriptions, locations, contacts, languages, keyword text/order and validated filter values. Empty filter values remain empty.
- Candidate row numbers are sequential positions in this separate file only; they are not database IDs. The mapping report stores the source row number, original parsed cells and candidate field mapping for each record. Stage 1’s `CSV-###` audit labels are not used.

## Validation

`test_csv_alignment_candidate.py` contains six offline `unittest` tests. It checks:

1. Exact 10-column header and uniform candidate row widths.
2. Standard-library CSV round-trip for values containing commas, quotes and newlines.
3. Candidate-to-source-row mapping and original parsed-cell preservation.
4. Keyword reconstruction and filter suffix placement without category/filter shifting.
5. Required fields, language and filter vocabularies, SQLAlchemy column lengths, and construction of `SupportResource` objects from candidate records.
6. Explicit ambiguity reporting and unchanged original-file SHA-256.

Executed with:

```powershell
python docs\csv_alignment_repair\test_csv_alignment_candidate.py
```

**Result: 6 tests passed.** A separate parser check confirmed that all 46 candidate records have exactly 10 cells. These tests do not load or write database records.

## Deliverables

- `resources_repaired_candidate.csv` — candidate only; do not treat as production input until reviewed and approved.
- `csv_row_mapping_report.csv` — original row number, parsed field count, candidate status/position, raw parsed cells, candidate field mapping and reconstruction note.
- `csv_ambiguous_rows.csv` — header-only because no row met the ambiguity criteria; any unresolved record would have been excluded from the candidate and listed here.
- `test_csv_alignment_candidate.py` — isolated offline checks.

**Recommended next action:** review the candidate and its six reconstructed filter rows, then approve or request changes before any separate implementation or database-loading stage. Do not run the production loader as part of this stage.
