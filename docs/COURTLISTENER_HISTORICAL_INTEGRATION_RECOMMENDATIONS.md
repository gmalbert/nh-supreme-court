# CourtListener Historical Corpus Integration Recommendations

## Executive recommendation

Granite State Appeals should incorporate the CourtListener corpus covering
1980–2001, but it should do so as a provenance-aware historical layer behind a
new canonical application data contract. The historical records should not be
copied directly into `data/processed/opinions.csv`, and the combined
`nh-case-law` digest should not replace the current Granite State Appeals
dataset until the two modern baselines have been reconciled.

The recommended division of responsibility is:

```text
nh-case-law
  CourtListener acquisition, normalization, extraction, validation,
  historical compilation, and immutable release handoff
        |
        v
Granite State Appeals
  app-owned canonical adapter, browse/search/detail UI, exports,
  and analytics that respect field availability
```

This adds substantial research value while protecting the existing justice,
vote, oral-argument, attorney, and lower-court analytics from fabricated or
misleading historical fields.

## Current findings

### Historical corpus quality

The `nh-case-law` workspace contains a strong historical source layer:

- 3,888 CourtListener clusters covering every year from 1980 through 2001.
- 0 records outside the requested date range.
- 0 records without usable text.
- 0 invalid dates.
- 3,888 records with Harvard/CAP provenance.
- 3,888 records classified as published.
- All historical extraction artifacts accepted and validated.

The detailed source audit is in
`nh-case-law/artifacts/courtlistener/audit/audit.json`. The extraction and
merge design is documented in
`nh-case-law/docs/COURTLISTENER_HISTORICAL_INTEGRATION.md`.

### Why the combined digest is not yet an application drop-in

The reviewed combined artifact contains 8,617 records:

| Corpus | Records | Intended role |
|---|---:|---|
| CourtListener historical | 3,888 | 1980–2001 research corpus |
| `nh-case-law` modern extraction corpus | 4,729 canonical | Research/extraction corpus |
| Combined artifact | 8,617 | Staging/research artifact |
| Current GSA `opinions.csv` | 2,809 | Existing application baseline |

The 4,729 modern records are not equivalent to the 2,809 rows currently used
by Granite State Appeals. The extraction corpus also has different identifiers,
metadata coverage, and derived fields. The combined artifact currently has
many missing modern citations and a small number of missing modern decision
dates. A report stating that the merge is safe does not eliminate the need for
modern-source reconciliation when the overlap checks lack complete metadata.

The current Granite State Appeals branch named
`data/add-cases-from-1980-2002` is presently at the same commit as `main`; the
historical data has not yet been wired into the application.

## Product scope

### Include in the first release

- Search and browse for historical cases by case name, docket, citation, year,
  topic, and extracted legal content.
- Case detail pages with summary, holdings, cited propositions, issue tags,
  source paragraphs, and a CourtListener source link.
- Full-text display only when the historical source text has been packaged and
  made available through a portable local or hosted path.
- Source-family and data-completeness indicators.
- CSV/JSON export with stable IDs and provenance fields.
- Historical cases in research-oriented search, citation exploration, related
  cases, and workspace features.

### Exclude or scope carefully in the first release

Historical records should not be included in metrics requiring fields they do
not possess:

- justice voting rates and panel diagrams;
- dissent/concurrence statistics;
- oral-argument, transcript, and attorney analytics;
- lower-court reversal statistics;
- outcome-prediction training or inference;
- term-level metrics that assume complete modern metadata.

These panels should either remain modern-only or calculate from an explicit
`has_<field>` eligibility flag. Missing data must render as “Unavailable,” not
as zero, false, or an inferred value.

## Canonical application data contract

Create an app-owned normalized dataset rather than forcing historical data into
the current flat CSV shape.

### Required fields

| Field | Historical value | Modern value | Notes |
|---|---|---|---|
| `record_id` | `courtlistener_<cluster_id>` | Existing stable source ID | Primary key for all app features |
| `source_family` | `courtlistener` | `granite_state_appeals` | Required and filterable |
| `case_name` | CourtListener/CAP caption | GSA caption | Required |
| `case_number` | Historical docket where available | GSA docket/source key | Nullable for exceptional records |
| `citation` | Reporter citation | GSA citation when available | Nullable; never synthesized casually |
| `date_issued` | CourtListener date | GSA date | ISO date or null |
| `summary` | Extracted digest summary | GSA summary or extracted summary | Mark as generated/derived |
| `holdings` | Extracted holdings | Extracted holdings where available | Source-anchored |
| `topics` | Mapped issue taxonomy | Existing topics plus mapped taxonomy | Preserve source vocabulary |
| `source_url` | CourtListener opinion URL | Official NH Courts PDF URL | Required where available |
| `text_relpath` | Packaged CAP text path | Packaged GSA text path | Must be portable, not absolute |
| `external_ids` | Cluster, docket, opinion IDs | Existing external keys | JSON object |
| `data_completeness` | Historical availability flags | Modern availability flags | Drives UI and analytics |

Suggested completeness structure:

```json
{
  "has_source_text": true,
  "has_source_url": true,
  "has_summary": true,
  "has_holdings": true,
  "has_votes": false,
  "has_justice_attribution": false,
  "has_oral_argument": false,
  "has_lower_court": false
}
```

Use `record_id` for routing, search indexes, embeddings, workspace references,
and exports. Dockets and captions are display/search attributes, not identity.

## Recommended implementation phases

### Phase 0 — Freeze and hand off the source

Produce a dated, checksummed handoff from `nh-case-law` containing:

- the 3,888 historical records;
- the merge report and source audit;
- a historical manifest;
- portable source text or hosted text URLs;
- taxonomy/version metadata;
- artifact hashes and release ID.

Do not make Granite State Appeals depend on a sibling checkout at runtime.

The historical text currently uses absolute paths inside the `nh-case-law`
workspace. Convert those to release-relative paths or a stable object-storage
URL before application use. The 47 MB historical text collection is small
enough to package separately from the digest/index files.

### Phase 1 — Reconcile the modern baseline

Build a machine-readable comparison between:

- current GSA `opinions.csv` / `all_opinions.json`;
- the modern records in the `nh-case-law` aggregate.

Classify each difference as:

- shared record;
- GSA-only record;
- extraction-only record;
- duplicate/alias;
- metadata mismatch;
- unresolved review candidate.

Use stable source IDs, docket aliases, official URLs, citations, normalized
captions, and dates. Do not deduplicate by case name alone. Matching reporter
citation or caption should create a review signal, not an automatic merge.

The output should explicitly identify which source is authoritative for each
modern field. The existing GSA metadata should remain authoritative for votes,
justices, oral arguments, lower courts, attorney data, and official PDF links.

### Phase 2 — Build the app-owned canonical dataset

Add a deterministic builder in Granite State Appeals that consumes the approved
handoff and produces an app-local JSON or Parquet release. A compatibility CSV
may be generated for legacy pages, but it should not be the canonical store.

Add validation for:

- unique `record_id` values;
- valid source-family prefixes;
- date range and ISO date format;
- source URL/path availability;
- required historical fields;
- no absolute paths in released records;
- stable sorting and byte-stable rebuilds;
- completeness flags consistent with actual values.

### Phase 3 — Add a shared loading layer

Extend `utils/data_loader.py` with functions such as:

```python
load_corpus_opinions() -> pd.DataFrame
load_corpus_record(record_id: str) -> dict | None
load_corpus_text(record_id: str) -> str
```

Keep `load_opinions()` as the compatibility path during rollout. Add a feature
flag such as `NH_COMBINED_CORPUS_ENABLED` so the prior 2,809-row behavior
remains an immediate rollback option.

All opinion-oriented pages should eventually receive the same canonical data,
rather than independently reading CSV, JSON, text, or derived indexes.

### Phase 4 — Migrate features in dependency order

1. **Opinions browser:** add year range 1980–present, source-family filter,
   citation/name/docket search, and historical source badges.
2. **Case detail:** route by `record_id`; display historical summary, holdings,
   date, citation, source link, and explicit unavailable fields.
3. **Search:** rebuild lexical, semantic, and dense indexes from the canonical
   corpus. Key embeddings by `record_id`, not only docket number.
4. **Legal Intelligence:** include historical records in research search and
   citation/related-case workflows, but exclude incomplete records from
   vote-dependent modules.
5. **Topics:** map historical issue tags to the GSA taxonomy and distinguish
   direct tags from inferred/derived tags.
6. **Dashboard and analytics:** use eligibility filters for every statistic;
   do not mix historical nulls into modern denominators.
7. **Exports/API:** expose `record_id`, `source_family`, `source_url`,
   `data_completeness`, and release metadata.

### Phase 5 — Stage and release

Run the combined corpus locally or in staging with the feature flag enabled.
Keep the prior data release and flag-off configuration intact. Promote only
after automated checks and manual case-detail checks pass.

## File-level impact in Granite State Appeals

| Area | Current behavior | Required change |
|---|---|---|
| `utils/data_loader.py` | Reads `opinions.csv`; text keyed by docket filename | Add canonical corpus loader and source-aware text resolver |
| `pages/01_Opinions.py` | 2000-present filter and current-schema fields | Use canonical fields, source filter, completeness-safe rendering |
| `cases.py` | Dashboard and detail assume votes/term fields | Scope metrics and route by stable record ID |
| `pages/02_Justices.py` | Justice/vote analytics | Modern eligible records only |
| `pages/03_Analysis.py` | Descriptive outcome/vote analysis | Add explicit eligible denominators |
| `pages/04_Topics.py` | Existing topic columns | Map historical taxonomy and label derived topics |
| `pages/07_Trial_Courts.py` | Lower-court analysis | Exclude unavailable historical lower-court fields |
| `pages/11_Compare_Cases.py` | Text lookup by current docket | Resolve both sources through canonical IDs |
| `pages/13_Legal_Intelligence.py` | Current dataframe and retrieval assets | Use canonical search and preserve module eligibility |
| `api/nh_courts_api.py` | Endpoints query `load_opinions()` | Add source-family, record-ID, provenance, and completeness support |
| `utils/data_releases.py` | Manifest assumes flat opinion export | Version the canonical corpus and include source coverage |
| `.github/workflows/refresh-data.yml` | Refreshes GSA sources only | Consume approved historical release without re-extracting it |

## Search and index recommendation

Do not make the GSA app consume `nh-case-law`’s `ResearchRepository` directly.
That index is coupled to the `nh-case-law` taxonomy and digest schema. Likewise,
the GSA-side CourtListener `build_indexes()` helper is currently a scaffold; it
creates a minimal SQLite schema but does not connect to the current GSA loaders
or pages.

Instead, define one GSA canonical index build from the app-owned release:

- lexical FTS index over name, citation, summary, holdings, propositions,
  topics, and optionally source text;
- semantic/dense index keyed by `record_id`;
- metadata tables for date, source family, completeness, and provenance;
- citation edges with unresolved targets retained and labeled;
- release ID and source hashes in index metadata.

Every derived index must be rebuilt from the same release input. Never pair a
new combined JSON with an older index.

## Validation gates

### Data gates

- Exactly 3,888 historical records in the handoff.
- Every year 1980–2001 represented.
- Every historical record has a valid date, source ID, and source text or URL.
- No duplicate `record_id` values.
- No released absolute filesystem paths.
- Modern reconciliation report accounts for every difference.

### Search/detail gates

- Historical name search returns the expected case.
- Historical reporter citation search returns the expected case.
- Historical docket search works where a docket exists.
- Modern regression searches remain unchanged with the flag off and valid with
  the flag on.
- Historical detail displays summary, holdings, date, source link, and
  unavailable-field labels without exceptions.
- Full-text retrieval works from the packaged or hosted source.

### Analytics gates

- Historical records do not enter justice/vote denominators unless eligible.
- Missing outcomes are not counted as reversals, affirmances, or zeros.
- Oral-argument and attorney panels do not claim historical coverage they do
  not possess.
- Outcome-prediction training excludes records without the required features.
- Dashboard totals identify both total corpus size and source-family coverage.

### Release gates

- Canonical output is reproducible and hashable.
- JSON/Parquet, text, and all SQLite indexes share one release ID.
- Old artifacts remain available for rollback.
- Staging uses a separate artifact root or service.
- Production changes only after manual sign-off and release verification.

## Final decision

Proceed with integration, prioritizing a unified historical search and case
browser. Treat the CourtListener material as a high-quality, open-access
historical research source, not as a source of retroactive vote, justice,
argument, attorney, or lower-court facts.

The safest first release is therefore:

1. preserve the existing GSA dataset and analytics;
2. import the 3,888 historical records through an app-owned adapter;
3. expose source and completeness metadata on every record;
4. rebuild search and research indexes from one canonical release;
5. expand analytics only when the underlying historical fields are genuinely
   available.

This delivers the practical benefit of 1980-present legal research while
keeping provenance, reproducibility, and analytical validity visible to users.
