# CourtListener Historical Corpus Integration Plan

## Purpose

Add the CourtListener-sourced New Hampshire Supreme Court corpus for 1980 through
2001 to the existing Granite State Appeals-backed corpus (principally 2002 to
present), without overwriting either corpus or losing source provenance.

This document records the post-cleanup status reviewed on September 4, 2026 and
defines the safe path from raw CourtListener records to one app-searchable
corpus.

## Review findings

### Source corpus

The CourtListener import is a sound source layer and is ready to be used as the
historical corpus.

| Check | Result |
| --- | --- |
| Requested coverage | January 1, 1980–December 31, 2001 |
| Normalized CourtListener clusters | 3,888 |
| Years with no cases | 0 |
| Records without usable text | 0 |
| Invalid or out-of-range dates | 0 |
| Conflicting duplicate reporter citations | 0 |
| Harvard/CAP provenance | 3,888 (100%) |
| Precedential status | Published for all records |

The original audit is retained at
`artifacts/courtlistener/audit/audit.json`; its year-by-year count is in
`artifacts/courtlistener/audit/coverage_by_year.csv`.

### Extraction status

CourtListener artifacts deliberately live under `artifacts/courtlistener/`,
apart from the modern-corpus artifacts under `artifacts/`. This isolation
prevented an incomplete historical run from changing the live application.

The extraction cleanup is complete:

| Stage | Records | Status |
| --- | ---: | --- |
| Validated and accepted historical extractions | 3,888 | Ready for aggregation |
| Rejected historical extractions | 0 | None |
| Outstanding historical extraction failures | 0 | None |
| Unattempted historical manifest entries | 0 | None |

The accepted production gates partition the 3,888-record manifest as follows:

| Gate | Accepted records |
| --- | ---: |
| `cl-gate-100` | 100 |
| `cl-gate-500` | 500 |
| `cl-gate-1000` | 500 |
| `cl-gate-2000` | 1,000 |
| `cl-gate-3000` | 1,000 |
| `cl-gate-4000` | 788 |
| **Total** | **3,888** |

`cl-gate-4000` is now fully cleaned: all 788 records are successful and
validated accepted, and its `failures.jsonl` is empty. The earlier
`cl-gate-050` run was a gate/pilot, is not part of this partition, and must not
be counted as additional corpus coverage.

## Why the files cannot simply be copied into the live corpus

The application reads the aggregate file:

```text
artifacts/compiled/case_digests.json
```

The generic compiler currently compiles one run at a time. Its CourtListener
output at:

```text
artifacts/courtlistener/compiled/case_digests.json
```

contains only the last explicitly compiled run (currently 1,000 records), not
all accepted CourtListener runs. Replacing the main aggregate with that file
would remove the modern corpus.

Also, `jp.compile.compile_aggregates()` emits the extraction digest fields but
does not retain source-manifest fields such as `date_issued`, `text_path`,
`external_ids`, or CourtListener opinion-type relationships. Those fields are
needed for correct date facets, source links, source-quote retrieval, and
reconciliation.

## Integration principles

1. Keep source corpora separate. Raw CourtListener cases, normalized text, and
   per-request extraction artifacts remain in `artifacts/courtlistener/`.
2. Keep per-request artifacts authoritative. Aggregates and indexes are derived
   and may always be rebuilt.
3. Use `source_document_id` as the canonical identity. CourtListener records
   use `courtlistener_<cluster_id>` and cannot collide with modern source IDs.
4. Do not deduplicate by case name. A name may recur, represent a consolidated
   matter, or be formatted differently by the two sources.
5. Treat a matching reporter citation across sources as a review signal, not
   an automatic merge. The planned time ranges should be disjoint, but this
   audit protects against boundary overlap and source-date errors.
6. Preserve the original CourtListener text, cluster/opinion IDs, CAP fields,
   and CourtListener URLs. Generated summaries are discovery aids, not the
   source of legal authority.
7. Do not publish a combined corpus until the historical extraction has passed
   the same validation gates as the modern corpus.

## Implementation plan

### 1. Preserve the completed extraction record

All 3,888 historical manifest entries now have accepted extraction artifacts.
Before aggregation, reconcile each gate from its per-request JSON files only if
needed to confirm that its JSONL ledger matches the normalized-artifact
directory. Do not rerun accepted cases merely to create the combined corpus.

The 17 existing source exceptions are quality flags (`short_text` or
`long_document`), not missing records. They remain part of the 3,888-record
source corpus and should remain visible in source-quality reporting.

### 2. Build an all-runs CourtListener compiler

Add a dedicated, deterministic compiler rather than using the one-run `compile`
command repeatedly.

It should:

1. Read every `artifacts/courtlistener/runs/*/normalized/*.json` artifact.
2. Include only artifacts with `success == true` and
   `validation_accepted == true`.
3. Canonicalize by `source_document_id`, preferring the accepted record with the
   richest extraction output; use a stable final tie-breaker such as run ID and
   request ID.
4. Join each canonical digest to the matching row in
   `artifacts/courtlistener/canonical_manifest.jsonl`.
5. Emit a historical aggregate that includes both extraction data and source
   metadata:

```json
{
  "source_document_id": "courtlistener_8091655",
  "case_number": "No. 94-434",
  "case_name": "Appeal of Barry",
  "citation": "141 N.H. 170",
  "date_issued": "1996-10-08",
  "text_path": ".../artifacts/courtlistener/text/courtlistener_8091655.txt",
  "external_ids": {
    "docket_id": "...",
    "cluster_id": "8091655",
    "opinion_ids": ["8091655"]
  },
  "related_records": [],
  "summary": "...",
  "holdings": [],
  "cited_propositions": [],
  "validation": {"accepted": true, "errors": [], "warnings": []}
}
```

6. Write an audit report containing input counts, accepted/rejected counts,
   duplicate source IDs, chosen/discarded run IDs, missing manifest joins, and
   source-text paths that do not exist.

The compiler must be idempotent: the same inputs produce the same ordered
records and audit report.

### 3. Build a combined application aggregate

Create a separate combined output first, for example:

```text
artifacts/compiled/combined_case_digests.json
```

Its inputs are:

- the current modern aggregate, `artifacts/compiled/case_digests.json`;
- the completed historical aggregate from Step 2; and
- source metadata manifests for both sources.

The merge process should:

1. Canonicalize each input by `source_document_id`.
2. Refuse duplicate IDs unless the rows are byte-equivalent or an explicit
   source-precedence rule resolves them.
3. Produce, but do not automatically collapse, a boundary-overlap report for
   matching normalized reporter citations or matching docket/date/name tuples.
4. Require historical `date_issued` values to fall from 1980 through 2001 and
   modern values to be outside that range, except explicitly reviewed records.
5. Sort the combined records by date, then citation, then source ID.
6. Emit a merge report with source counts, canonical count, collisions,
   unresolved overlaps, and date-range coverage.

Only after that report has no unreviewed collisions should the combined output
replace the live `case_digests.json` (or the application should be configured
to use the combined file explicitly).

### 4. Rebuild dependent indexes

Once the combined digest is approved, rebuild all derived search/index artifacts
from the same combined input:

- `research_index.db`;
- `case_digests_fts.db`;
- citation proposition and citation-edge indexes; and
- any taxonomy coverage, primer, or analytics reports.

The index build must receive metadata that contains both source families. The
current default metadata file is the Granite State Appeals `all_opinions.json`,
which does not contain CourtListener rows. The combined source manifest should
therefore be provided explicitly to the research-index build.

### 5. Verify before switching the app

Run these checks against the combined artifacts:

- canonical record count equals the modern canonical count plus 3,888 historical
  records, less only documented boundary duplicates;
- every historical year from 1980 through 2001 has indexed cases;
- a search for a historical case name and citation returns the expected result;
- the case detail view opens its local source text and provides a valid
  CourtListener opinion link;
- modern-case search results and citation links remain available;
- topic counts and citation-edge counts change only in ways explained by the
  historical addition; and
- all source-text paths, dates, and external IDs pass a filesystem/schema audit.

Keep the pre-switch aggregate and index as a timestamped backup until the
combined corpus passes UI smoke tests and legal-content spot checks.

## Existing relevant files

| File | Role |
| --- | --- |
| `scripts/courtlistener/normalize_cases.py` | CourtListener CSV-to-cluster normalization |
| `scripts/courtlistener/build_cl_manifest.py` | Bridge to the extraction pipeline and source-text writer |
| `scripts/courtlistener/audit_coverage.py` | Historical coverage audit |
| `src/jp/compile.py` | Existing per-run aggregate compiler; preserves extraction fields only |
| `src/jp/research_index.py` | Canonicalization and SQLite research-index builder |
| `scripts/build_research_index.py` | Index entry point; must receive combined metadata |
| `review_app.py` | Already recognizes CourtListener source IDs and constructs opinion links |

## Definition of done

All 3,888 CourtListener clusters are now successfully extracted and validated.
They are incorporated only when the all-runs compiler has produced a
provenance-rich historical aggregate, the combined merge report has no
unreviewed collisions, and the research/search indexes and application have
been rebuilt and verified against that combined aggregate.
