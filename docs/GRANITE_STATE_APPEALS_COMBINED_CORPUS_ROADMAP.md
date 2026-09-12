# Granite State Appeals Combined-Corpus Roadmap

## Objective

Make the Granite State Appeals application capable of searching, displaying,
and analyzing the approved combined New Hampshire Supreme Court corpus:

| Source | Intended coverage | Canonical records |
| --- | --- | ---: |
| Existing Granite State Appeals dataset | Primarily 2002-present | 2,805 currently displayed by this app |
| CourtListener historical corpus | 1980-2001 | 3,888 |

This is an application-integration project, not a file-copy operation. The
CourtListener combined digest currently exists in the sibling `nh-case-law`
workspace and uses a different schema from this application's
`data/processed/opinions.csv` and `all_opinions.json` model.

## Current state

- The running Granite State Appeals dashboard reads
  `data/processed/opinions.csv` through `utils/data_loader.py` and therefore
  correctly displays 2,805 opinions.
- It has no configured path to the combined digest, CourtListener source text,
  or CourtListener provenance metadata.
- The reviewed combined corpus contains 8,617 records in total (4,729 modern
  canonical records plus 3,888 historical records). That modern count is not
  expected to match this application's 2,805-row CSV until the modern-source
  reconciliation described below is complete.
- The historical corpus and its provenance-preserving compiler should remain
  isolated from this app until the adapter and validation gates pass.

## Principles and non-goals

1. Preserve both source datasets and their identifiers. Do not overwrite the
   current CSV or replace historical source text with generated summaries.
2. Keep provenance visible on every historical record: CourtListener URL,
   cluster/opinion identifiers, source text path, and source family.
3. Use an app-owned, versioned derived dataset. The app should not reach into
   a sibling workspace at runtime.
4. Treat apparent records that overlap by citation, docket, date, or caption
   as review candidates, not automatic deduplications.
5. Roll out in read-only and feature-gated stages; the current 2,805-opinion
   experience remains the rollback path until the integrated experience is
   accepted.

Out of scope for the first release: backfilling unavailable vote data,
argument data, justice attribution, lower-court data, or PDF metadata for
historical decisions. These must be represented as unavailable, never inferred.

## Phase 0 — establish a reproducible source handoff

**Deliverables**

- A dated, checksummed export of the approved combined digest and its merge
  report from `nh-case-law`.
- A source manifest containing record count, source family, date coverage,
  text locations, external identifiers, and artifact hashes.
- A dated backup of this app's `opinions.csv`, `all_opinions.json`, search
  artifacts, and the current application build metadata.

**Acceptance gates**

- The handoff contains exactly 8,617 canonical rows and 3,888 historical rows.
- Every historical row has a usable text source and valid issue date.
- The handoff is copied into an app-owned `artifacts/` or `data/derived/`
  location, not referenced across workspaces.

## Phase 1 — reconcile the modern baseline

The two modern datasets have different counts (4,729 in the combined corpus
versus 2,805 in Granite State Appeals). Integrating historical material safely
requires understanding this difference before presenting a single total.

**Work**

1. Canonicalize each modern source by stable source ID, docket aliases, and
   official citation.
2. Produce a reconciliation table classifying every difference as one of:
   shared, duplicate, app-only, combined-only, or metadata mismatch.
3. Review boundary years and duplicate reporter citations manually.
4. Decide which source is authoritative for each app-facing modern field.

**Acceptance gates**

- The total to be displayed is explained by a machine-readable reconciliation
  report, not a simple addition of incompatible input-row counts.
- No record is silently discarded because its caption or citation is similar
  to another record.

## Phase 2 — define the application canonical schema and adapter

Create a new normalized record model rather than forcing CourtListener data
into `opinions.csv` without provenance or pretending all fields are available.

**Minimum canonical fields**

| App field | Modern source | Historical source | Notes |
| --- | --- | --- | --- |
| `record_id` | Existing stable key | `courtlistener_<cluster_id>` | Immutable primary key |
| `source_family` | `granite_state_appeals` | `courtlistener` | Required on every row |
| `case_name`, `case_number`, `citation`, `date_issued` | Existing metadata | Combined digest/manifest | Required for browsing and facets |
| `summary`, `topics`, `word_count` | Existing/app-derived | Combined digest | Mark generated fields as derived |
| `source_url`, `text_path`, `external_ids` | Official PDF/local text where available | CourtListener/local text/IDs | Required for provenance |
| votes, justice fields, oral arguments, lower court | Existing where available | Nullable | Never fabricate historical values |

**Work**

1. Add a deterministic build script that consumes the approved handoff and
   produces an app-local JSON/Parquet canonical dataset plus a flat CSV only
   where existing pages require one.
2. Version the schema and validate required fields, types, identifiers,
   source-family rules, and text paths.
3. Keep unavailable fields nullable and add an explicit `data_completeness`
   indicator so pages can suppress unsupported analytics.
4. Add unit tests for mapping a representative modern case and a representative
   CourtListener case, including `Appeal of Barry`, 141 N.H. 170.

**Acceptance gates**

- Rebuilding from identical handoff inputs yields byte-stable sorted outputs.
- Every historical record retains its CourtListener link and source text.
- Existing modern case detail links remain valid.

## Phase 3 — evolve the shared data-loading layer

Update `utils/data_loader.py` behind a feature flag (for example,
`NH_COMBINED_CORPUS_ENABLED`) so all opinion-oriented pages receive the same
canonical dataset.

**Work**

1. Add `load_corpus_opinions()` and `load_corpus_record()`; retain
   `load_opinions()` during the transition for pages not yet migrated.
2. Key Streamlit caches on the canonical artifact version and modification
   time.
3. Provide compatibility fields for current views while each page migrates.
4. Add safe text resolution for both the existing local source files and
   CourtListener text; expose external source URLs as provenance links.

**Acceptance gates**

- With the flag off, behavior and count remain the current 2,805 records.
- With the flag on, loaders return the approved canonical count and no page
  attempts to dereference a missing historical PDF, vote, or argument field.

## Phase 4 — migrate user-facing features in dependency order

1. **Opinions and Case Explorer:** source-family filters, year/citation/name
   search, record detail, local text, CourtListener source link, and clear
   unavailable-field presentation.
2. **Dashboard:** replace the hard-coded corpus count with the active canonical
   count and display coverage/source breakdown. Do not mix unsupported
   historical records into term-only metrics.
3. **Search and Legal Intelligence:** rebuild search indexes from the canonical
   dataset; test historical title, citation, and full-text retrieval.
4. **Topics and Analysis:** include historical material only for measures that
   are valid with available fields. Keep justice, dissent, oral-argument, and
   similar panels scoped to records that contain those data.
5. **Exports and API:** include `record_id`, `source_family`, provenance URL,
   and completeness information.

## Phase 5 — quality assurance and staged release

**Automated checks**

- Schema, count, date-range, ID-uniqueness, and source-text audits.
- Every year from 1980 through 2001 appears in the historical slice.
- Historical search by name and citation; modern regression searches; source
  URL validation; no broken detail pages.
- Page-specific analytics tests that ensure nullable historical fields do not
  distort denominator calculations.

**Manual smoke checks**

- Review historical, modern, and boundary-year cases in the browser.
- Confirm a historical detail view opens its local text and CourtListener link.
- Confirm current dashboards and justice/argument panels retain their prior
  behavior for records outside their available-data scope.

**Release sequence**

1. Build artifacts and run tests offline.
2. Enable the feature flag in a local/staging run; verify the displayed count
   and source breakdown.
3. Preserve the prior artifacts and flag-off configuration as the rollback.
4. Promote only after manual sign-off; record the artifact version, canonical
   count, and validation report in release notes.

## Definition of done

Granite State Appeals has a reproducible, app-local combined corpus; its
displayed total is backed by a reconciled canonical count; historical opinions
are searchable and attributable to CourtListener; modern functionality remains
intact; and source-limited analytics explicitly exclude or label records that
lack the required data.
