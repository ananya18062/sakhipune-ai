# SakhiPune AI resource trust and filter implementation plan

**Status:** planning only. No CSV, code, tests, schema, database, or deployment setting was changed.

## 1. Evidence-supported corrections

These are the only three exact replacements recorded in the remediation proposal with direct official evidence. All require approval before any data edit.

| Record / field | Current value | Proposed value | Supporting official source |
|---|---|---|---|
| Yuva Karya Prashikshan, original/candidate row 26 — application instruction in `description` | “Apply through District Skill Development Office Pune.” | “Register as a job seeker at `https://rojgar.mahaswayam.gov.in`.” | [Pune District scheme page](https://pune.gov.in/en/scheme/mukhyamantri-yuva-karya-prashikshan-yojana) specifies candidate registration on Mahaswayam. The source supports the route; current cycle availability still needs checking. |
| Yuva Karya Prashikshan, original/candidate row 26 — programme wording in `description` | “6-month paid internship-style job training” | “Six-month job training” | [Pune District scheme page](https://pune.gov.in/en/scheme/mukhyamantri-yuva-karya-prashikshan-yojana) uses “Job Training” and states six months. This avoids relabeling it as an internship without source support. |
| PM Ujjwala Yojana, original/candidate row 35 — `contact` (URL) | `https://pmujjwalayojana.com` | `https://pmuy.gov.in` | [Official PMUY portal](https://pmuy.gov.in) is the government portal identified in the evidence audit; the `.com` URL is not official. This corrects the URL only; no benefits, eligibility, or application wording is approved by this evidence. |

The official references and claims above match the remediation proposal’s correction register (E1 and E8). No other exact replacement is proposed. In particular, the JSY summary, education entitlement, Ladki Bahin current status, PMUY benefits, contacts, filter values, or any inaccessible-source URL remain unresolved.

## 2. Minimum safeguards against unsupported eligibility filters

**Confirmed current behavior:** `SupportResource` stores `experience_level`, `work_mode`, and `employment_type` as nullable strings. The loader maps non-empty CSV values directly and does not validate them against evidence. The category services apply strict matching (including excluding unknown metadata) on jobs and internships; the main frontend calls `/api/recommend`, which ranks all resources without those strict filters. The candidate’s 18 populated filter values remain inconclusive in the existing review.

**Proposed minimum change:**

1. Treat these resource-side values as eligibility/opportunity claims, not as user preferences. Do not translate a user answer such as “Student or fresher” into an eligibility assertion about a resource unless the user explicitly selects a requirement filter and that resource attribute has been verified.
2. Do not use a stored filter value for inclusion/exclusion unless its evidence is approved. Safest initial implementation: require the resource’s review state to be `verified` before any of its structured fields can satisfy or exclude a strict filter. Pending/unknown values behave as unknown, not as a match. Do not fabricate replacement values or alter the current candidate during implementation planning.
3. Validate request filter tokens against the model’s controlled vocabularies in Pydantic (the existing validator only strips/lowercases); reject unsupported tokens explicitly. Apply filters only to jobs/internships, and reject or ignore-by-documented-contract filter fields on unrelated categories rather than silently giving them inconsistent effects.
4. Make internship employment-type behavior explicit. Either apply it through the same shared job-filter function when provided, or reject that field for internships until supported. Do not silently accept a filter that the endpoint ignores.
5. Keep ranking preference signals separate from strict eligibility filters. Preferences may rank suitable options; they must not claim that a user meets scheme eligibility or that a resource accepts a given experience level.

These rules are proposed design choices, not current behavior. The owner must approve whether unknown filter metadata is excluded from strict matches (recommended for safety) and how an empty filtered result is explained.

## 3. Resource review and recommendation state

**Confirmed:** existing reports distinguish verified, partially verified, unverified, incorrect, and inaccessible. No resource currently meets the report’s complete verification threshold. The SQLAlchemy model and API response do not carry a reviewed provenance state to the frontend.

**Minimum proposed mechanism:** add a small, explicit trust/provenance record to each resource in a later approved schema migration:

- `review_status`: controlled values `pending_verification`, `verified`, `temporarily_withheld`; set all existing rows to `pending_verification` on migration. Never infer `verified` from a working URL or from a prior “partially verified” label.
- `source_url`, `source_name`, `last_verified_at`, and concise `verification_notes`: nullable evidence fields. Keep the date null until a human actually checks the claim.
- Define `verified` to mean that every material claim intended for display—including contact/location, eligibility and any filter value being used—is directly supported by an appropriate source. If only part is supported, leave the record pending and explain the supported subset in notes.

At recommendation time, exclude `temporarily_withheld` records. Pending records should not be presented as verified. Do not automatically suppress every pending critical-support record: initially require an approved, source-checked contact before showing actionable emergency/legal/healthcare/shelter directions; otherwise keep it in an internal review queue and use only a separately verified fallback. For lower-impact resources, owner approval may allow a clearly labeled “verification pending” informational result with its source/caveat. The fallback and display policy requires approval; no alternative contact is supplied here.

This schema is a proposal only. Existing records should be initialized as pending, with no backfill of sources or dates unless the corresponding claim was actually reviewed. Consider a separate richer evidence-status field only if retaining the existing partial/unverified/incorrect/inaccessible classification in the database is required; it is not needed to begin safely with `pending_verification`.

## 4. Minimum API and frontend filter wiring

**Confirmed current path:** `frontend/js/app.js` builds `preferences` from adaptive answers and posts to `/api/recommend`. The typed `experience_filter`, `work_mode_filter`, `employment_type_filter`, and `delivery_mode_filter` fields exist in `SupportRequest`, but are not included in that payload. `/api/jobs` and `/api/internships` merge typed fields into preferences and call filter services; `/api/route` currently passes only `user_query.preferences` to the category router and therefore misses typed fields.

**Proposed minimum change, preserving the existing stack and service structure:**

1. Use the existing category-routed `/api/route` endpoint for the frontend’s job and internship requests (or keep `/api/recommend` as the UI endpoint and implement the same dispatch there; choose one contract, do not maintain two different semantics). Prefer `/route`, which already dispatches to the category services.
2. In `route_recommend`, merge the typed filter fields into preferences using the existing helper before calling `route_query`. Ensure the route’s employment and internship services receive the same normalized filter keys as `/api/jobs` and `/api/internships`.
3. In the vanilla-JS question flow, expose explicit filter selections whose values map to the allowed tokens. Send only filters the user deliberately selected; “open to options” and missing answers mean no filter. Do not map “flexible hours,” “near my area,” or “student” to remote/on-site/eligibility values without a separately approved, semantically correct mapping.
4. Pass only verified resource metadata to the shared filter function. Ensure the `employment_type_filter` contract is either implemented for internships or rejected there, not silently dropped.
5. Add verified/pending state and source/caveat to the recommendation response and display a concise status/source on resource cards. Hide withheld records. This should be wired through normalized resources and `_dict_to_orm` as needed so category and full recommendation paths behave consistently.

The existing category router is the narrowest place to reuse for category-specific filtering; central recommendation filtering/trust gating must still cover `/recommend` or that endpoint must be retired only with explicit compatibility approval. The API contract and any endpoint switch are owner decisions before implementation.

## 5. Essential regression tests

- Pydantic accepts each supported token, normalizes case/whitespace, rejects unknown tokens, and treats omitted/blank fields as no filter.
- A resource with verified filter metadata matches the requested value; pending or unknown metadata cannot produce a positive eligibility match or be used to exclude a resource silently.
- `temporarily_withheld` resources never reach recommendations; pending resources are labeled and follow the approved category-specific policy; no row becomes verified by default.
- The three approved field replacements are applied only to the approved copy and round-trip without modifying original data or unapproved candidate values.
- `/recommend`, `/route`, `/jobs`, and `/internships` apply the agreed request contract consistently; category-irrelevant filters are handled explicitly.
- Employment type is either correctly applied for internships or returns a clear validation error; it is never silently ignored.
- Frontend submits only explicitly selected filter values, preserves “no filter” choices, and renders status/source/caveat safely using DOM text APIs.
- Regression for non-job categories, empty result sets, duplicate resources, and existing ranking behavior when no filters are supplied.

## 6. Implementation order and approval gates

| Order | Work | Safe to begin without changing production? | Approval required |
|---:|---|---|---|
| 1 | Approve the three exact text/URL corrections above; apply them only to a separate reviewed candidate and compare against the original. | Preparation on a new copy is safe; changing either existing CSV is not authorized. | Yes — approve each proposed correction. |
| 2 | Decide trust-state meanings, pending/critical fallback policy, filter eligibility semantics, and endpoint contract. | Design/test planning only. | Yes — these are behavioral and user-impact decisions. |
| 3 | Add nullable provenance/trust fields with a migration default of `pending_verification`; test on an isolated disposable database. Do not connect to Neon. | Isolated migration/test work is safe after design approval. | Yes — schema change and status policy. |
| 4 | Add API validation, one consistent filter path, verified-only filter matching, and response provenance. | Local code changes/tests are safe after contract approval. | Yes — endpoint behavior and unknown-filter policy. |
| 5 | Add vanilla-JS filter choices/payload mapping and status/source display; run focused backend and frontend regression tests. | Local implementation/testing after API contract approval. | Yes — user-facing workflow/display decision. |
| 6 | Review results and stage a non-production load plan; verify row mappings, existing record behavior, and no unintended duplicate inserts. | No production load. | Separate explicit approval required for any Neon/production access or load. |

**Smallest next implementation task:** after approval, create a separate corrected-candidate copy containing only the two Yuva description edits and PMUY URL correction, run a field-level diff against the current candidate and original, and stop for review. This is the smallest isolated change; do not load it into any database.

**Unresolved blockers:** approval of the exact corrections; policy for displaying pending critical resources; whether filter metadata is eligibility or preference; whether internship employment type should be supported; choice of frontend endpoint contract; and any future schema migration. No plan item authorizes production database access.
