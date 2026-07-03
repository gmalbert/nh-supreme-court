# Granite State Appeals — Consolidated Product Roadmap

**Status:** Canonical roadmap for unfinished features  
**Last reviewed:** 2026-07-02  
**Scope:** All unfinished or partially implemented features proposed across the repository documentation, reconciled against the current codebase.

This document supersedes the feature ordering in `03_features.md`, `06_phased_plan.md`, `6_MONTH_FEATURES.md`, `NEXT_FEATURES.md`, `MODEL_SUGGESTED_ENHANCEMENTS.md`, and the future-enhancement sections of the oral-argument feature documents. Those files remain useful design history, but several of their status statements are stale.

## How to use this roadmap

- **P0** work closes foundational research and data-refresh gaps.
- **P1** work adds the highest-value research workflows after the foundations exist.
- **P2** work deepens oral-argument analysis.
- **P3** work covers retention, delivery, accessibility, and performance.
- Complete work in dependency order within a priority unless a feature explicitly says otherwise.
- Add tests with every feature. New generated data must be reproducible from a checked-in script or workflow.

## Already implemented and excluded from the backlog

The following older suggestions are already present and should not be reimplemented:

- Oral-argument transcript viewer, transcript search, snippets, filters, text/Markdown downloads, and Vimeo links.
- Oral-argument statistics, attorney and firm profiles, attorney/firm comparisons, speaker-role statistics, trends, and attorney–justice interaction views.
- Opinion metadata search and filters, filtered CSV export, docket-based case selection, and official opinion PDF links.
- Justice profiles, voting records, authorship views, and a basic agreement heatmap.
- Trial-court outcome/reversal analysis and decision-timing analysis.
- Topics, RSA tracking, case orders, and opinion/oral-argument linking by docket.
- Scheduled post-refresh validation and scheduled UI validation.

Primary existing implementations:

- `cases.py`
- `pages/01_Opinions.py`
- `pages/02_Justices.py`
- `pages/03_Analysis.py`
- `pages/04_Topics.py`
- `pages/05_Case_Orders.py`
- `pages/07_Trial_Courts.py`
- `pages/08_Oral_Arguments.py`
- `pages/09_Attorney_Detail.py`
- `pages/10_Firm_Detail.py`
- `utils/data_loader.py`
- `utils/oral_arguments.py`
- `utils/charts.py`
- `.github/workflows/post-refresh-maintenance.yml`
- `.github/workflows/weekend-ui-validation.yml`

---

## P0 — Core research and data foundations

### P0.1 Full-text opinion search

**Status:** Partial. Search currently covers metadata, summaries, RSA citations, lower courts, and topics—not complete opinion bodies.

**Deliverables**

- Build a persistent SQLite FTS5 opinion index with case number, citation, name, full text, summary, topics, author, outcome, and year.
- Support phrase search, stemming/tokenization, ranked results, highlighted snippets, and filters.
- Use one search service from both the dashboard and Opinions page.
- Rebuild incrementally when opinion text or metadata changes.
- Provide an empty-query browse state and clear no-result/error states.

**Related existing code/data**

- `cases.py`: `_search_tokens`, `_search_blob`, `_search_opinions`, `_render_search_result`, `_render_description_search`.
- `pages/01_Opinions.py`: current case-name/RSA search and result table.
- `utils/data_loader.py`: `load_opinion_text`, `load_opinions`, and `load_opinions_json`.
- `scripts/parse_opinions.py`: `extract_text` and parsed opinion fields.
- `data/processed/text/`: extracted opinion text, where available.
- `data/processed/opinions.csv` and `data/processed/all_opinions.json`.

**Planned code**

- Add `scripts/build_search_index.py`.
- Add `utils/opinion_search.py` with index-open, query, filter, and snippet functions.
- Update `pages/01_Opinions.py` and `cases.py` to use the shared service.
- Add `data/processed/opinions_fts.sqlite` to generated artifacts; decide whether it is checked in or rebuilt at deployment.
- Add `tests/test_opinion_search.py`.

**Acceptance criteria**

- A phrase present only in full opinion text returns the correct case.
- Results are ranked and show highlighted context.
- Year, topic, author, and outcome filters compose correctly.
- The index is reused rather than rebuilt on each Streamlit rerun.

### P0.2 Automated incremental opinion ingestion

**Status:** Partial. Local pipeline scripts and scheduled validation exist; GitHub Actions does not fetch and commit new opinions.

**Deliverables**

- Add a scheduled and manually dispatchable refresh workflow.
- Scrape opinion and order indexes, download only new/changed PDFs, parse, rebuild derived datasets and indexes, and run validation.
- Record additions, updates, failures, and the source refresh timestamp in a machine-readable manifest.
- Open an issue or fail visibly when scraping/parsing health thresholds are breached.
- Commit generated changes only when validation passes and data changed.
- Regenerate oral-argument derived statistics when oral-argument data changes.

**Related existing code/data**

- `scripts/update.py`: local pipeline coordinator.
- `scripts/scrape_index.py`, `scripts/scrape_3jx.py`, and `scripts/scrape_orders_index.py`.
- `scripts/download_pdfs.py`, `scripts/parse_opinions.py`, and `scripts/build_dataset.py`.
- `scripts/refresh_oral_arguments.py`, `scripts/extract_speaker_stats.py`, `scripts/extract_attorney_stats.py`, `scripts/generate_enhanced_stats.py`, and `scripts/analyze_attorney_justice_interactions.py`.
- `update_pipeline.ps1` and `download_log.txt`.
- `.github/workflows/post-refresh-maintenance.yml`: rebuild/validation only.
- `.github/workflows/weekend-ui-validation.yml`: tests and browser validation only.

**Planned code**

- Add `.github/workflows/refresh-data.yml`.
- Add `scripts/refresh_manifest.py` or extend `scripts/update.py` to emit `data/processed/refresh_manifest.json`.
- Add explicit `--check`, `--since`, and/or idempotent modes where missing.
- Update `requirements.txt` only if the workflow introduces a new runtime dependency.

**Acceptance criteria**

- A no-change run produces no commit.
- A new opinion is fetched, parsed, indexed, tested, and surfaced without manual steps.
- A parser regression prevents publication and leaves an actionable workflow summary.
- The refresh timestamp reflects source ingestion, not a page-render time.

### P0.3 Citation extraction, internal links, and citation index

**Status:** Not implemented.

**Deliverables**

- Extract reported and neutral NH case citations from opinion text.
- Resolve extracted citations to canonical `case_number` values where possible.
- Preserve unresolved/ambiguous citations with confidence and source context.
- Display linked cited cases on case detail pages and backlinks (“cited by”).
- Produce reusable node/edge data for the later graph and recommender.

**Related existing code/data**

- `scripts/parse_opinions.py`: text extraction and opinion record construction.
- `scripts/build_dataset.py`: normalization and master dataset generation.
- `utils/data_loader.py`: opinion and opinion-text loaders.
- `cases.py`: case-detail rendering.
- `data/processed/all_opinions.json` and extracted opinion text.

**Planned code**

- Add `utils/citations.py` with citation parsing, normalization, and resolution.
- Add `scripts/build_citation_index.py`.
- Add `data/processed/citations.json` and `data/processed/citation_edges.csv`.
- Update `cases.py` with “Cites” and “Cited by” sections.
- Add `tests/test_citations.py` using real formatting variants.

**Acceptance criteria**

- Known citations resolve deterministically to the correct internal case.
- Unresolved references are never silently linked to a fuzzy match.
- Citation and backlink lists agree for every resolved edge.

### P0.4 Case-order to opinion cross-linking

**Status:** Not implemented in the Case Orders UI.

**Deliverables**

- Normalize docket numbers across orders and opinions.
- Add opinion-match status and links to the orders table and detail view.
- Show related orders from the opinion case page.
- Support one-to-many relationships and unmatched orders.

**Related existing code/data**

- `pages/05_Case_Orders.py`.
- `utils/data_loader.py`: `load_case_orders`, `load_opinions`, and empty-schema helpers.
- `utils/oral_arguments.py`: `normalize_docket_numbers`, reusable for canonical docket logic.
- `scripts/scrape_orders_index.py`, `scripts/build_dataset.py`.
- `data/processed/case_orders.csv`, `data/processed/3jx_orders.csv`, and `data/processed/opinions.csv`.

**Planned code**

- Add a shared docket-normalization helper if `normalize_docket_numbers` cannot safely cover orders.
- Add `scripts/build_case_relationships.py` or extend `scripts/build_dataset.py`.
- Add `data/processed/case_relationships.json`.
- Update `pages/05_Case_Orders.py` and `cases.py`.
- Add `tests/test_case_relationships.py`.

**Acceptance criteria**

- Exact docket matches link both directions.
- Combined/consolidated dockets link to every relevant case.
- Unmatched records remain visible and explicitly labeled.

### P0.5 Global data freshness and parsing-error reporting

**Status:** Partial. `data_last_updated()` exists, but the planned information and reporting controls are not consistently available across pages.

**Deliverables**

- Create a shared sidebar/footer component showing last successful source refresh, coverage range, opinion count, court link, and refresh health.
- Add a prefilled “Report a parsing error” GitHub issue link carrying docket and page context.
- Distinguish dataset freshness from oral-argument freshness.

**Related existing code**

- `utils/data_loader.py`: `data_last_updated`.
- `footer.py`.
- `cases.py` and every file under `pages/`.
- Planned `data/processed/refresh_manifest.json` from P0.2.

**Planned code**

- Add `utils/site_chrome.py` or extend `footer.py` with shared `render_data_status()` and `render_error_report_link()` functions.
- Replace page-specific freshness displays with the shared component.
- Add focused rendering/helper tests where practical.

**Acceptance criteria**

- Every page presents the same source refresh date and health state.
- Error-report links include enough context to identify the record.

---

## P1 — High-value research workflows

### P1.1 Similar-cases recommender

**Dependencies:** P0.1; benefits from P0.3.

**Deliverables**

- Return the five most similar earlier cases using full text, summary, topics, RSA citations, and citation relationships.
- Explain each recommendation with shared topics, statutes, citations, or matching terms.
- Prevent the current case and future-dated cases from appearing when using a historical-research mode.

**Related existing code/data**

- `utils/data_loader.py`: opinions and full-text loaders.
- `pages/04_Topics.py`: topic/RSA parsing and filtering patterns.
- `cases.py`: case detail.
- P0.1 search index and P0.3 citation index.

**Planned code**

- Add `scripts/build_similarity_index.py`.
- Add `utils/similar_cases.py`.
- Add a “Similar cases” section to `cases.py`.
- Add `tests/test_similar_cases.py`.

**Acceptance criteria**

- Recommendations are deterministic for a fixed dataset.
- Every result includes a human-readable reason.

### P1.2 Plain-language decision summaries

**Status:** Not implemented. Existing `summary_paragraph` values are extracted legal text, not generated explanations.

**Deliverables**

- Generate a concise “what happened / legal question / result” summary.
- Store model/provider/version, generation date, source hash, and review status.
- Clearly label generated text and retain the extracted source summary separately.
- Regenerate only when source text or summarization configuration changes.
- Provide a non-AI fallback when no generated summary exists.

**Related existing code/data**

- `scripts/parse_opinions.py`: `get_summary_paragraph` and `clean_summary_text`.
- `scripts/build_dataset.py`: summary normalization.
- `cases.py` and `pages/01_Opinions.py`: current summary rendering.
- `data/processed/all_opinions.json` and full opinion text.

**Planned code**

- Add `scripts/generate_plain_summaries.py`.
- Add `data/processed/plain_summaries.json`.
- Add `load_plain_summaries()` to `utils/data_loader.py`.
- Update `cases.py` and `pages/01_Opinions.py`.
- Add schema/provenance tests; avoid tests that require live model access.

**Acceptance criteria**

- Generated and extracted summaries cannot be confused in the UI or schema.
- Generation is resumable, cached by source hash, and auditable.

### P1.3 Opinion comparison tool

**Status:** Not implemented. Existing attorney/firm comparisons do not compare cases.

**Deliverables**

- Select two opinions and compare metadata, outcomes, justices/votes, topics, RSA citations, summaries, timing, citations, and opinion text side by side.
- Support a shareable query-string URL.
- Optionally highlight shared and differing terms after P0.1.

**Related existing code**

- `cases.py`: case rendering and query-parameter routing.
- `pages/01_Opinions.py` and `pages/04_Topics.py`.
- `utils/data_loader.py`.

**Planned code**

- Add `pages/11_Compare_Cases.py`.
- Add reusable comparison formatting in `utils/case_comparison.py` if needed.
- Add comparison navigation from case detail pages.
- Add tests for query parsing and comparison-field normalization.

**Acceptance criteria**

- The comparison survives reload through URL parameters.
- Missing fields do not break either column.

### P1.4 Annual report generator

**Status:** Not implemented.

**Deliverables**

- Generate a downloadable annual PDF containing opinion totals, outcomes, reversal rates, divided decisions, timing, topics, authorship, lower courts, and methodology notes.
- Use the same calculations as the interactive pages.
- Include report generation date and dataset source refresh date.

**Related existing code**

- `pages/03_Analysis.py`, `pages/07_Trial_Courts.py`, and `utils/charts.py`.
- `utils/data_loader.py`.

**Planned code**

- Add `utils/annual_report.py` and `scripts/generate_annual_report.py`.
- Add a download control to `pages/03_Analysis.py`.
- Add snapshot/data tests for report sections and a PDF smoke test.
- Add the chosen PDF dependency to `requirements.txt`.

**Acceptance criteria**

- Report totals match the UI for the same year and dataset.
- The generated PDF has no clipped tables/charts and includes methodology caveats.

### P1.5 Advanced justice-agreement exploration

**Status:** Partial. A 5×5 heatmap exists; drill-down and topic filtering do not.

**Deliverables**

- Add topic, case type, and year filters to agreement calculations.
- Selecting a justice pair should reveal shared cases and disagreements.
- Show shared-case denominator and suppress misleading low-sample comparisons.

**Related existing code**

- `pages/02_Justices.py`: `_build_agreement_matrix` and Agreement Matrix tab.
- `utils/charts.py`: `agreement_heatmap`.
- `utils/vote_parser.py`.

**Planned code**

- Extract agreement calculation into `utils/justice_analysis.py`.
- Extend `pages/02_Justices.py` with filters and pair detail.
- Add `tests/test_justice_agreement.py`.

**Acceptance criteria**

- Matrix and detail rows use the same eligible-case set.
- Every rate visibly includes its denominator.

<!-- ### P1.6 Geographic analysis

**Status:** Not implemented.

**Deliverables**

- Normalize origin courts to county/municipality where defensible.
- Map appeal volume and reversal rate by county.
- Expose unknown/unmapped records rather than discarding them.

**Related existing code/data**

- `pages/07_Trial_Courts.py`.
- `scripts/parse_opinions.py`: lower-court extraction.
- `scripts/build_dataset.py`: lower-court normalization.
- `data/processed/opinions.csv`.

**Planned code**

- Add `data/nh_court_geography.json` with documented provenance.
- Add `utils/geography.py`.
- Add a Geography section or tab to `pages/07_Trial_Courts.py`.
- Add mapping and aggregation tests.

**Acceptance criteria**

- Coverage and unknown counts are displayed.
- Map totals reconcile with the underlying filtered data. -->

### P1.7 Counsel outcome and specialization analytics

**Status:** Partial. Appearance, duration, firm, network, and justice-interaction analytics exist; opinion outcomes and legal-topic specialization are not joined reliably.

**Deliverables**

- Join oral arguments to opinions by normalized docket.
- Calculate appearance outcomes by attorney, firm, side, case type, and topic with clear denominators.
- Add topic-specialization and justice-specific interaction views.
- Avoid describing an appellate disposition as an attorney “win” unless side/outcome mapping is reliable; label uncertain records.

**Related existing code/data**

- `pages/08_Oral_Arguments.py`, `pages/09_Attorney_Detail.py`, and `pages/10_Firm_Detail.py`.
- `scripts/extract_attorney_stats.py`, `scripts/generate_enhanced_stats.py`, and `scripts/analyze_attorney_justice_interactions.py`.
- `utils/data_loader.py`: oral-argument, attorney, interaction, and opinion loaders.
- `data/attorney_name_map.json`, `data/firm_metadata.json`.
- `data/processed/oral_arguments*.json` and `data/processed/opinions.csv`.

**Planned code**

- Add `scripts/build_counsel_outcomes.py`.
- Add `data/processed/counsel_outcomes.json`.
- Add loader support and new sections to oral-argument/attorney/firm pages.
- Add join, side-mapping, and denominator tests.

**Acceptance criteria**

- Every displayed rate exposes matched, unmatched, and uncertain counts.
- Consolidated dockets and multiple attorneys do not inflate case counts silently.

---

<!-- ## P2 — Oral-argument analysis

### P2.1 Named-justice speaker statistics

**Status:** Not implemented. Current extraction classifies speakers broadly as Justice, Counsel, or Other.

**Deliverables**

- Identify individual justices only when transcript/audio evidence supports it.
- Preserve confidence, unknown-speaker labels, and correction overrides.
- Add per-justice speaking time, words, pace, turns, and questions.

**Related code/data**

- `scripts/extract_speaker_stats.py`.
- `pages/08_Oral_Arguments.py`: `_render_reader` and `_render_statistics`.
- `utils/data_loader.py`: `load_speaker_statistics`.
- `data/justices.json` and `data/processed/oral_arguments/`.

**Planned code**

- Add `scripts/identify_argument_speakers.py` or extend speaker extraction.
- Add `data/oral_argument_speaker_overrides.json`.
- Extend the speaker-statistics schema and UI.
- Add confidence/override tests. -->

### P2.2 Interruption and questioning analysis

**Dependencies:** Benefits from P2.1.

**Deliverables**

- Define reproducible turn-taking, interruption, and question metrics.
- Display aggregate trends and per-argument breakdowns.
- Clearly disclose limitations caused by inferred timestamps/speaker labels.

**Related code/data**

- `scripts/extract_speaker_stats.py` and transcript segment timestamps.
- `pages/08_Oral_Arguments.py`.
- `docs/scoring-methodology.md` for existing transcript-quality heuristics.

**Planned code**

- Add `scripts/analyze_argument_turns.py`.
- Add `data/processed/oral_argument_turn_stats.json` and loader support.
- Add algorithm tests with synthetic turn sequences.

### P2.3 Case-type and longitudinal speaker analysis

**Dependencies:** P1.7 for reliable opinion/topic linkage.

**Deliverables**

- Compare speaking time, pace, questions, and interruptions across years, topics, and case types.
- Include sample sizes and distribution views rather than averages alone.

**Related code/data**

- `pages/08_Oral_Arguments.py`: `_render_trends_analysis` and speaker charts.
- `scripts/generate_enhanced_stats.py` and `scripts/extract_speaker_stats.py`.
- Opinion/oral-argument join from P1.7.

**Planned code**

- Extend enhanced-stat generation and the Trends tab.
- Add aggregation tests.

### P2.4 Transcript text-analysis tools

**Status:** Partial. Search snippets exist; visual term highlighting, readability, keyword extraction, topic modeling, and word clouds do not.

**Deliverables**

- Highlight search terms in transcript results and reader view.
- Add readability and keyword extraction with documented formulas.
- Add optional topic/term visualizations only when they improve interpretation.

**Related code**

- `utils/oral_arguments.py`: `make_search_snippet` and `search_oral_arguments`.
- `pages/08_Oral_Arguments.py`: `_render_reader` and `_render_transcript_search`.
- `utils/data_loader.py`: oral-argument text/Markdown loaders.

**Planned code**

- Add `utils/text_analysis.py` and shared safe-highlighting logic.
- Extend oral-argument stats artifacts and UI.
- Add escaping, Unicode, and metric tests.

### P2.5 Transcript formats and embedded media

**Status:** Partial. Text/Markdown downloads and external Vimeo links exist; PDF/DOCX and embedded playback do not.

**Deliverables**

- Generate accessible PDF and DOCX transcripts with case metadata and machine-generated-transcript disclaimers.
- Embed media only where Vimeo permissions and Streamlit support allow it; retain the external link fallback.

**Related code**

- `pages/08_Oral_Arguments.py`: `_render_reader` download and Vimeo controls.
- `utils/data_loader.py`: transcript artifact loaders.
- `data/processed/oral_arguments/markdown/` and `text/`.

**Planned code**

- Add `utils/transcript_export.py`.
- Add PDF/DOCX dependencies to `requirements.txt`.
- Add export smoke tests and accessibility metadata checks.

### P2.6 Co-counsel relationship graph

**Status:** Partial. Aggregate attorney-network statistics exist, but no interactive attorney–firm–case/co-counsel graph exists.

**Deliverables**

- Build co-appearance edges with case counts and years.
- Filter by firm, attorney, year, and case type.
- Provide a table fallback and cap interactive graph size.

**Related code/data**

- `scripts/generate_enhanced_stats.py`: `analyze_attorney_networks`.
- `scripts/extract_attorney_stats.py`.
- `pages/08_Oral_Arguments.py`, `pages/09_Attorney_Detail.py`, and `pages/10_Firm_Detail.py`.
- `data/processed/oral_arguments_enhanced_stats.json`.

**Planned code**

- Extend network artifact generation with explicit nodes/edges.
- Add `utils/network_charts.py` if the graph cannot live cleanly in `utils/charts.py`.
- Add network views and aggregation tests.

---

## P3 — Retention, delivery, polish, and scale

### P3.1 Bookmarks and favorites

**Deliverables:** Add session-state case bookmarks, a bookmarked-cases view, clear/remove controls, and later optional persistent storage.  
**Related code:** `cases.py`, `pages/01_Opinions.py`, and Streamlit query/session state.  
**Planned code:** Add `utils/bookmarks.py` and bookmark controls to case/result components.  
**Acceptance:** Bookmarks survive page navigation during a session and never mutate source data.

### P3.2 Keyword, RSA, and topic alerts

**Dependencies:** P0.1 and P0.2.

**Deliverables:** Define saved watch rules, match only newly ingested opinions, prevent duplicate notifications, and support an initial email transport.  
**Related code:** Search service from P0.1, refresh manifest from P0.2, `pages/04_Topics.py`.  
**Planned code:** Add `utils/watch_rules.py`, `scripts/evaluate_watches.py`, a subscription/settings UI, and a secure deployment-time mail configuration.  
**Acceptance:** Re-running the same refresh does not resend an alert.

<!-- ### P3.3 Webhook notifications

**Dependencies:** P0.2; share matching/deduplication with P3.2.

**Deliverables:** Send a concise new-opinion payload to configured Discord-compatible webhooks with retries and deduplication.  
**Planned code:** Add `utils/notifications.py` and a post-refresh workflow step. Store secrets only in deployment secret storage.  
**Acceptance:** Failed webhooks do not corrupt ingestion, and retries do not duplicate successful deliveries. -->

### P3.4 Recent-decisions component

**Status:** Partial. The dashboard has opinion data but no dedicated last-ten ticker/list matching the roadmap request.

**Deliverables:** Show the ten latest decisions with issue date, case name, outcome, and links; update automatically with the dataset.  
**Related code:** `cases.py`: `render_dashboard`; `utils/data_loader.py`: `load_opinions`.  
**Planned code:** Add a reusable `render_recent_decisions()` component.  
**Acceptance:** Ordering is deterministic and gracefully handles missing dates.

### P3.5 Responsive mobile layout

**Deliverables:** Audit every page at common phone/tablet widths; replace brittle wide columns, provide scrollable/fallback tables, keep filters reachable, and enlarge tap targets.  
**Related code:** `cases.py`: `_style_dashboard`; `pages/08_Oral_Arguments.py`: `_style_page`; compact chart helpers in `pages/07_Trial_Courts.py`; all Streamlit pages.  
**Planned code:** Centralize responsive CSS/components in `utils/site_chrome.py`; extend `validate_ui.py` with mobile viewports.  
**Acceptance:** Core browse/search/case/transcript flows work without clipped controls at supported widths.

### P3.6 Accessibility and keyboard navigation

**Deliverables:** Semantic headings, meaningful link/button labels, sufficient contrast, keyboard-operable controls, chart/table alternatives, screen-reader text, and visible focus states.  
**Related code:** All page renderers, `utils/charts.py`, and `validate_ui.py`.  
**Planned code:** Add accessibility assertions to browser validation and an accessibility checklist to the About page.  
**Acceptance:** Automated checks pass and primary workflows can be completed keyboard-only.

### P3.7 Theme, chart customization, and onboarding

**Deliverables:** Respect system/light/dark themes where Streamlit permits, centralize chart colors, and add a dismissible first-run tour or concise onboarding panel.  
**Related code:** `.streamlit/config.toml`, `cases.py`, page-specific CSS, and `utils/charts.py`.  
**Planned code:** Add shared theme tokens/components; avoid maintaining separate page-local palettes.  
**Acceptance:** Text/charts meet contrast requirements in every supported theme.

### P3.8 Performance and offline-readiness

**Status:** Deferred until profiling identifies real bottlenecks.

**Candidate work**

- Use `st.fragment` for isolated expensive rerenders.
- Virtualize or paginate large result sets.
- Move large query workloads to SQLite.
- Compress JSON artifacts where deployment transfer size warrants it.
- Evaluate offline/service-worker support only if compatible with the deployment model.

**Related code**

- Cached loaders in `utils/data_loader.py`.
- Large tables in `pages/01_Opinions.py`, `pages/05_Case_Orders.py`, and `pages/08_Oral_Arguments.py`.
- Search database from P0.1.

**Planned code**

- Add repeatable performance measurements before optimizations.
- Record page-load/query budgets in validation output.

**Acceptance criteria**

- Optimizations are backed by before/after measurements.
- No offline layer is added unless cache invalidation and data freshness are explicit.

---

## Dependency sequence

1. **Automate and describe the data:** P0.2 and P0.5.
2. **Make the corpus searchable and connected:** P0.1, P0.3, and P0.4.
3. **Build research workflows:** P1.1 through P1.7.
4. **Deepen transcript analysis:** P2.1 through P2.6.
5. **Add retention and delivery:** P3.1 through P3.4.
6. **Polish and scale from evidence:** P3.5 through P3.8.

Features within a stage may proceed in parallel when they do not share schema changes.

## Cross-cutting engineering requirements

Every roadmap item must include:

- A documented schema for any generated artifact.
- Provenance and generation timestamps for derived/AI-generated data.
- Deterministic regeneration where possible.
- Graceful handling of missing, unmatched, and ambiguous records.
- Unit tests for parsing/calculation logic and browser validation for critical UI paths.
- Updates to `README.md` and relevant methodology documentation.
- No committed credentials, API keys, webhook URLs, or private archive paths.
- Clear labeling for machine-generated transcripts, inferred speakers, generated summaries, and heuristic outcome mappings.

## Code ownership map

| Area | Current code | Roadmap impact |
|---|---|---|
| Dashboard and case detail | `cases.py`, `footer.py` | Search, citations, similar cases, summaries, relationships, freshness, bookmarks, recent decisions |
| Opinion browsing | `pages/01_Opinions.py` | Full-text search, snippets, bookmarks, comparison entry points |
| Justice analysis | `pages/02_Justices.py`, `utils/charts.py`, `utils/vote_parser.py` | Filtered agreement and pair drill-down |
| Court analytics | `pages/03_Analysis.py`, `pages/07_Trial_Courts.py` | Annual reports and geography |
| Topics/RSA | `pages/04_Topics.py` | Search filters, recommendations, alerts |
| Orders | `pages/05_Case_Orders.py` | Order/opinion cross-linking |
| Oral arguments | `pages/08_Oral_Arguments.py`, `pages/09_Attorney_Detail.py`, `pages/10_Firm_Detail.py` | Counsel outcomes, speaker/turn/text/media/network analysis |
| Data loading | `utils/data_loader.py`, `utils/oral_arguments.py` | New indexes, artifacts, shared joins, freshness manifest |
| Opinion pipeline | `scripts/scrape_index.py`, `scripts/download_pdfs.py`, `scripts/parse_opinions.py`, `scripts/build_dataset.py`, `scripts/update.py` | Automated ingestion, search/citation/similarity artifacts |
| Order pipeline | `scripts/scrape_orders_index.py`, `scripts/scrape_3jx.py` | Automated ingestion and case relationships |
| Oral-argument pipeline | `scripts/refresh_oral_arguments.py`, `scripts/extract_speaker_stats.py`, `scripts/extract_attorney_stats.py`, `scripts/generate_enhanced_stats.py`, `scripts/analyze_attorney_justice_interactions.py` | Regeneration, counsel outcomes, named speakers, turns, networks |
| CI and validation | `.github/workflows/`, `tests/`, `validate_ui.py` | Refresh automation, regression gates, accessibility/mobile/performance checks |
| Dependencies/config | `requirements.txt`, `.streamlit/config.toml` | Search, report/export, themes, deployment configuration |

## Definition of done

A feature is complete only when its code, generated artifacts, tests, UI integration, documentation, failure behavior, and refresh/update path are all implemented. A script or data file without a user-facing integration is **partial**; a UI backed by manually maintained derived data is also **partial**.
