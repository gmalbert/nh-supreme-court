# Granite State Appeals — Full-Site Improvement Audit

**Audit date:** 2026-07-16
**Scope reviewed:** Streamlit entry point, every public page and profile page, shared loaders/utilities, data-ingestion and analysis scripts, tests, requirements, workflows, existing roadmap/docs, and processed-data interfaces.
**Companion document:** `docs/ANALYTICS_OPPORTUNITIES.md` focuses specifically on oral argument → disposition research.

## Bottom line

Granite State Appeals has the raw material for a very useful public legal-research site: broad structured opinions, orders and 3JX data, oral-argument transcripts, attorney/firm records, court analytics, and several advanced utilities already in the repository. The biggest opportunity is not adding another isolated chart. It is to turn the existing assets into a **coherent, source-first research journey** with a reliable data contract, consistent page chrome, and a small number of deeply integrated workflows.

The highest-return sequence is:

1. Make research findings trustworthy and navigable: unified full-text search, source-linked case lifecycle, consistent freshness/methodology, and coverage labels.
2. Integrate existing utilities before inventing more: citations, related cases, bookmarks, responsive chrome, data-status/error reporting, and outcome/counsel analysis.
3. Establish reliable release/data-refresh discipline: a single canonical roadmap, reproducible artifacts, dependency-locked tests, and browser smoke tests.
4. Build the higher-order analytics described in the companion oral-argument roadmap.

## Evidence and audit notes

### What is already strong

- The navigation covers the core research surfaces: dashboard, case reader, opinions, justices, analysis, oral arguments, topics, orders/3JX, trial courts, and profiles.
- `utils/data_loader.py` offers a useful central loading/caching boundary and handles combined docket normalization for oral arguments.
- The case reader (`cases.py`) already brings together opinion metadata, PDF, bench/vote, counsel, oral argument, and citations.
- The oral-argument page has unusually rich collection-level data: searchable transcripts, attorney/firm activity, speaker metrics, trends, and comparisons.
- The data pipeline includes crosswalk, manifest-audit, reconciliation, citation, similarity, attorney-roster, and quality-review tools.
- The project has a substantial test suite and GitHub refresh/validation workflows.

### Important gaps or inconsistencies observed

- The README describes full-text opinion search, citation exploration, freshness status, and enhanced navigation as available, but the **Opinions Browser** still searches only case name/RSA/docket and the full-text search utility is not its primary search UI.
- Multiple useful utilities are present but not broadly wired into the public site: responsive/data-status chrome, error reporting, bookmarks, recommended similar cases, annual reports, text-analysis/export helpers, and some advanced justice/counsel/turn-taking analyses.
- Case Orders/3JX is a good browser but has no research-detail/lifecycle view and no surfaced related-opinion/oral-argument links.
- Page styling and freshness indicators are implemented independently. The dashboard, individual pages, and profile pages therefore do not consistently expose data status, limitations, report-error controls, or a common source treatment.
- Several pages are large, top-level scripts that mix data shaping, business rules, and rendering. This makes testing and future feature work expensive (especially `cases.py`, `pages/03_Analysis.py`, and `pages/08_Oral_Arguments.py`).
- Documentation is partly historical. For example, `docs/SITE_SUMMARY.md` and `docs/architecture.md` describe old page counts/paths and older operating assumptions, while `docs/ROADMAP.md` itself contains stale statuses for utilities that now exist.
- The test command cannot currently collect all tests in the inspected environment because `streamlit` and `plotly` are not installed. `python3 -m compileall` passes for application, utility, and script modules; `pytest -q` stops during collection with missing dependency errors.
- `pages/11_Compare_Cases.py` and `pages/12_Firm_Review.py` call `st.set_page_config()` even though the entrypoint has already configured the app and the project convention says configuration should be centralized. The firm-review page is also absent from navigation, which is reasonable only if it is intentionally maintainer-only and documented as such.

## Prioritization rubric

- **P0 / short term:** prevents misleading research results, improves reliability, or unlocks a core existing capability. Target: next 2–4 weeks.
- **P1 / medium term:** makes the site materially more useful for recurring research. Target: 1–3 months.
- **P2 / long term:** expands research depth, delivery, and institutional value after the foundations are stable. Target: 3–12 months.

## Short term (P0): make the current site coherent and trustworthy

### P0.1 Integrate one true opinion search experience

**Why:** This is the clearest gap between the public promise and public UI. The FTS infrastructure exists (`utils/opinion_search.py`, `scripts/build_search_index.py`), while the Opinions Browser currently filters metadata only.

**Deliverable:** Replace the free-text portion of `pages/01_Opinions.py` with an FTS-backed result path that composes with year, author, outcome, vote, topic, and case-type filters. Show result rank, a highlighted snippet, and a clear fallback if the index is unavailable.

**Code blueprint:** keep query logic out of the page and return normalized records from one service.

```python
# utils/research_service.py (new)
from utils.opinion_search import index_exists, search

def search_opinions(query: str, filters: dict[str, object], limit: int = 100) -> list[dict]:
    if not query.strip() or not index_exists():
        return []
    return search(query=query, limit=limit, **filters)

# pages/01_Opinions.py
if search_query.strip():
    results = search_opinions(search_query, selected_filters)
    render_search_results(results)  # citation, case link, highlighted context, score
else:
    render_browse_table(filtered)
```

**Acceptance checks:** a phrase found only in `data/processed/text/` appears in the browser; filters compose; a result links to the canonical Case Explorer; the empty/browse state remains fast and usable.

### P0.2 Create a case-lifecycle card and reuse it everywhere

**Why:** A researcher should not have to know whether a given docket became an opinion, case order, 3JX order, or oral argument record before discovering it.

**Deliverable:** Add a reusable `render_case_lifecycle(case_number)` component to the Case Explorer first, then reuse it in Case Orders/3JX and the oral-argument reader. It should show source records, dates, match method/confidence, argument/video, decision/order PDF, citations, and known unresolved status.

**Targets:** new `utils/case_lifecycle.py`; `cases.py`; `pages/05_Case_Orders.py`; `pages/08_Oral_Arguments.py`; use `utils.dockets`, `utils.case_resolution`, `case_docket_crosswalk.csv`, and `case_relationships.json`.

**Acceptance checks:** exact and combined dockets link correctly; uncertain links remain visibly uncertain; users can get from an order to related opinion/argument and back.

### P0.3 Adopt shared page chrome and transparent methodology controls

**Why:** The site needs one visible answer to “what data am I seeing, how current is it, and how do I report a problem?”

**Deliverable:** Make `utils/site_chrome.py` the single page wrapper: responsive CSS, data status, compact source/methodology disclosure, error-report link, and footer. Call it from every public route, not only the comparison page.

**Code blueprint:**

```python
# utils/site_chrome.py
def render_page_shell(*, page_name: str, case_number: str | None = None) -> None:
    render_responsive_css()
    render_data_status()
    render_error_report_link(case_number=case_number, page=page_name)

# each public page, after imports and before page content
render_page_shell(page_name="Opinions")
```

Use an appropriate location for the error link (sidebar on browse pages; case header on detail pages) so it does not overwhelm normal research.

### P0.4 Restore a reproducible test environment and release gate

**Why:** The full suite did not collect in the audit environment because the declared runtime dependencies were absent. A test suite that developers cannot launch predictably is not a dependable gate.

**Deliverable:** Add a documented bootstrap command and lock/reproducible environment (`requirements-dev.txt` or a pinned lockfile), then make the same command run locally and in CI. Keep production dependencies separate from optional NLP/ML dependencies.

**Recommended structure:**

```text
requirements.txt        # runtime UI/data dependencies
requirements-dev.txt    # -r requirements.txt, pytest, browser test tools, linters
requirements-ml.txt     # transformers, torch; optional, never required to run the site
```

**Acceptance checks:** a clean virtual environment can run `python3 -m pytest -q`; CI runs unit tests, builds derived data in check mode, then performs browser smoke tests against a local Streamlit server.

### P0.5 Remove configuration and navigation ambiguity

**Why:** App configuration should be declared once, and maintainers need a clear distinction between public, profile, and internal-review surfaces.

**Deliverable:** remove page-level `st.set_page_config()` calls from `pages/11_Compare_Cases.py` and `pages/12_Firm_Review.py`; decide whether Firm Review is maintainer-only (recommended) or add it to a protected/explicit review route; document the decision.

**Acceptance checks:** app starts without page-config warnings/errors; no public navigation leads to a write-like review form accidentally; maintainers know how to reach the review workflow.

### P0.6 Make data freshness and coverage source-specific

**Why:** an opinions CSV timestamp is not the same as oral-argument transcription freshness or a 3JX-order refresh.

**Deliverable:** extend `refresh_manifest.json` with per-source timestamps, coverage period, record counts, error counts, and last-success status. Render the relevant source status on each page.

**Suggested manifest shape:**

```json
{
  "generated_at": "2026-07-16T14:00:00Z",
  "sources": {
    "opinions": {"last_success": "...", "records": 2795, "coverage": "2002–2026"},
    "case_orders": {"last_success": "...", "records": 0, "coverage": "2014–2026"},
    "oral_arguments": {"last_success": "...", "records": 1173, "coverage": "2015–2026"}
  }
}
```

### P0.7 Repair documentation drift and declare one source of truth

**Why:** current docs can mislead contributors about pages, operating commands, and implementation status.

**Deliverable:** replace `docs/SITE_SUMMARY.md` with a short current orientation, refresh `docs/architecture.md`, and amend `docs/ROADMAP.md` to mark shipped infrastructure accurately while linking to this audit and the analytics roadmap. Keep a concise `docs/CONTRIBUTING.md` with setup, test, data-build, and deployment commands.

## Medium term (P1): complete core research workflows

### P1.1 Build a unified “Research Workspace” around a case, not a page type

Give every case/matter a consistent set of tabs or sections:

- **Overview:** source PDF, dates, court/lower court, outcome, vote, author, verified summary.
- **Procedural path:** oral argument, orders/3JX/opinion links, time-to-decision, match confidence.
- **People:** parties, counsel/advocate, firms at time of case, justices/panel; show evidence/source.
- **Law:** topics, RSA and constitutional issues, cited/citing decisions, similar earlier decisions.
- **Documents:** readable text, download, source PDFs, citations, and a shareable stable URL.

This can be a refactor of `render_case_explorer()` first; avoid creating a separate parallel “case detail” page.

### P1.2 Finish related-case, citation, and comparison workflows

The building blocks exist but need product integration.

- Show a small, explained “Related earlier cases” card in Case Explorer using `similarity_index.json`, never an unexplained score.
- Improve similarity-index input normalization so topic/RSA list fields do not yield empty recommendations.
- Add a citation explorer mode: outgoing/incoming citations, filters by year/topic, and source links; make unresolved citations inspectable rather than silently discarded.
- Let the Case Explorer open Compare Cases with the current case prefilled; make comparison deep links stable.
- In comparison, add side-by-side holding/summary, topic/RSA/vote/citation differences, and phrase search/synchronized text scrolling. Escape or render raw text safely rather than interpreting arbitrary extracted opinion text as Markdown.

### P1.3 Finish orders and 3JX as first-class research material

- Add an order detail panel with PDF, parsed summary, source category, signatories/panel, related opinion/argument links, and status of the docket match.
- Add order-type filters, date-range filter, full-text/order-summary search, issue/topic filters only when tags are sourced/reviewed.
- Explain 3JX in plain language and never conflate it with a conventional full opinion or an advocate outcome.
- Provide an “unmatched but investigated” workflow for maintainers based on the existing queues and manifest audit.

### P1.4 Turn profiles into research profiles, not only activity counters

- Attorney and firm pages: time-of-case firm association, source confidence, topic/case-type mix, lower-court mix, opponent ecosystem, argument-to-disposition profile, and carefully bounded observed outcome profile.
- Justice pages: historic as well as active roster selection, tenure-aware denominator, case links in vote records, confidence/coverage notes, and both rate and count in agreement views.
- Trial-court pages: minimum-case threshold, explicit lower-court parsing confidence, definition of reversal/mixed outcomes, downloadable filtered table and source links.
- Topic pages: trend and case list should link to case lifecycle; explain multi-tag counting; distinguish terms/topics derived by heuristics from manually reviewed categories.

### P1.5 Improve information architecture and findability

- Add a global command-style search entry point in the header: case/docket/citation, lawyer, firm, statute, and text search.
- Preserve filters in query parameters and add a “copy research link” action. Filter state should survive page navigation and be included in CSV exports.
- Add breadcrumbs and contextual cross-links rather than relying on users to discover a sidebar route.
- Make default page states purposeful: recent decisions, popular topics, current term, and “start with a docket” rather than empty tables or first 20 alphabetical records.
- Keep Profile routes either discoverable through search/navigation or explicitly label them as drill-down routes.

### P1.6 Deliver accessibility and mobile as tested features

- Apply `render_responsive_css()` consistently, then validate real Streamlit DOM behavior rather than relying only on CSS assumptions.
- Ensure chart alternatives: sentence summary, data table/download, accessible titles, color-independent labels, and keyboard reachable controls.
- Remove unsafe HTML where a native Streamlit component works; for retained HTML, escape data values before interpolation.
- Add a “plain view”/reduced-motion choice and ensure data tables are usable on narrow screens.
- Run automated accessibility checks plus keyboard and screen-reader spot checks on Dashboard, Opinions, Case Explorer, Oral Arguments, and Analysis.

### P1.7 Strengthen data integrity and editorial workflow

- Assign stable IDs to every input and generated record; record parser version, source URL, source checksum, and manual-override provenance in exports.
- Build review queues for low-confidence topic, counsel, docket, author/vote, and firm mappings; show queue aging and ownership.
- Add data contracts/schema tests for every generated CSV/JSON, including allowed enums and date/docket/list-field formats.
- Make automatic dataset rebuilding explicit in a build command/service rather than silently invoking `subprocess.run()` during a public page request. A stale-data warning is preferable to an invisible expensive rebuild.
- Preserve a changelog of record additions, corrections, and deletions across refreshes.

### P1.8 Operationalize the work already present

- Wire bookmarks into Case Explorer and Opinions Browser, with a clearly labelled browser-session scope; consider saved/shareable collections only after an authentication/privacy decision.
- Expose annual report generation as a maintainers’ build artifact and publish selected reports to `docs/reports/` or a static download location.
- Add transcript text/PDF/DOCX export controls only after confirming licensing/attribution language and rendering quality.
- Promote the firm-review tool into an explicit maintainers’ process with import/validation/reconciliation instructions, not an orphan page.

## Long term (P2): deepen research value and resilience

### P2.1 Oral-argument outcome analytics

Implement `docs/ANALYTICS_OPPORTUNITIES.md` in dependency order: canonical argument-disposition fact/bridge tables, outcome/timing explorer, profile/topic cross-tabs, then transcript and network research. Every outcome display must include linkage confidence, numerator, denominator, exclusions, and a descriptive—not causal—label.

### P2.2 Public research dataset and API-like contract

- Publish versioned CSV/Parquet bundles with data dictionary, terms of use, changelog, provenance, and reproducible build instructions.
- Offer stable downloadable slices for opinions, orders, arguments, people, topics, citations, and lifecycle links.
- Add a narrow read-only query interface only if the hosting/privacy model supports it; rate-limit and cache by query hash.
- Provide citations researchers can use: dataset version, record identifiers, access date, and source URL.

### P2.3 Better search and discovery

- Semantic/hybrid search as an optional complement to keyword/FTS, with exact-keyword results visible and a transparent explanation of matches.
- Natural-language research prompts translated into previewable filters, never silently into legal conclusions.
- “What changed this term?” briefings with explicit data cutoffs and links to every underlying record.
- Saved research collections, annotations, and alert/watch rules after explicit user-account/privacy design.

### P2.4 Institutional and doctrinal research views

- Citation-network and doctrinal-development timelines.
- Cohort/survival analysis for decision timing and docket throughput, stratified by case type/topic/disposition channel.
- Bench/author/panel trends with appointment-aware denominators and uncertainty disclosures.
- Repeat-litigant/agency/municipality views only after robust party normalization and ethical review.
- A provenance-first “Why this result?” drawer for each aggregate chart.

### P2.5 Platform resilience and maintainability

- Move derived research artifacts from scattered JSON files to a versioned local analytical store (SQLite/DuckDB/Parquet), while preserving easy static deployment exports.
- Use a layered architecture: loaders/repositories → domain services → view models/charts → Streamlit pages. Avoid data parsing in views.
- Add typed models (for example, Pydantic/dataclasses), a formatter/linter/type checker, and pre-commit hooks.
- Make scraper health observable: source-page snapshots, schema-change alerts, per-stage metrics, retry policy, and failure notifications.
- Add disaster-recovery instructions and a documented policy for upstream-source changes/removed PDFs.

## Page-by-page opportunities

| Surface | Short term | Medium/long term |
| --- | --- | --- |
| Dashboard | Make source freshness visible; replace fixed “2026 argument statistics” wording with actual coverage; add a true global search entry point. | Personalized/saved research starts; “what changed” briefing; curated explainers. |
| Case Explorer | Add lifecycle card, report-error link, related order/argument/citation source links, and safe document rendering. | Unified research tabs, similar cases, collection/bookmark/share workflows, provenance drawer. |
| Opinions Browser | Integrate FTS and snippets; add topic/case-type filters and stable filter URLs. | Search facets, saved searches, citation/semantic discovery. |
| Justices | Include historic roster selection, case links, and counts next to all rates. | Appointment-aware trend/cohort analytics and validated interaction research. |
| Analysis | Refactor each tab into service + renderer; surface coverage/exclusion notes on charts. | Argument Outcomes Explorer, annual term reports, transparent methods drawer. |
| Topics | Link each topic to lifecycle cases; explain multi-tag counting. | Precedent-gap, RSA/constitutional, and emerging-topic research. |
| Orders/3JX | Add detail/lifecycle links and clear 3JX explanatory copy. | Full-text search, order typology, panel/routing/timing analytics. |
| Trial Courts | Define metrics/denominators and add source/case links, thresholds, and confidence. | Court/judge cohorts and configurable, cautious comparisons. |
| Oral Arguments | Link all records to lifecycle/status, make speaker-label confidence easier to see. | Outcome/timing explorer; validated individual justice/question metrics; argument–opinion alignment. |
| Attorney/Firm Profiles | Show confidence and historical firm association; link to each case/argument directly. | Practice fingerprints, comparable-cohort outcome/timing profiles, opponent networks. |
| Compare Cases | Remove duplicate page config; prefill from case links; handle empty search results safely. | Diff, synchronized full-text search, citation/RSA/vote comparison and exports. |
| About/Methodology | Add per-source coverage, update policy, data dictionary, corrections policy. | Versioned methodology and reproducibility reports. |
| Firm Review | Explicitly define as maintainer-only and document input/output cycle. | Validated import workflow, review audit history, entity-resolution tooling. |

## Suggested code organization

The project does not need a rewrite. Refactor gradually around a few shared services:

```text
utils/
  repositories.py          # typed/cached reads of generated artifacts
  research_service.py      # opinion/argument/order query and filter composition
  case_lifecycle.py        # canonical cross-source case links and status
  presentation.py          # labels, number/date formatting, disclosure text
  site_chrome.py           # one page shell and metadata/error controls
  charts/                  # chart builders grouped by domain over time
pages/
  ...                      # input widgets + service call + rendering only
scripts/
  build_*.py               # explicit, idempotent artifact generation
tests/
  unit/ integration/ ui/ fixtures/
```

Small refactoring rules:

1. A page should not open files or call subprocesses.
2. A page should not decide how a docket aliases or how a result is classified.
3. Every chart function should receive a prepared view model/DataFrame and return a chart plus any needed disclosure metadata.
4. Every computed public metric should have a tested service function and an exportable table.
5. Move duplicated duration formatting, profile case-table construction, list parsing, labels, and sidebar status widgets into shared helpers.

## Safety, ethics, and communication requirements

- Preserve the site’s non-legal-advice posture and link every conclusion to official source material.
- Treat attorney/firm/justice comparisons as descriptive. Publish methodology, denominators, thresholds, unresolved counts, and data-quality caveats alongside rates.
- Do not make outcome predictions, score individual advocates, or infer motives from question counts, dissents, or recusal patterns.
- Avoid presenting machine transcripts and heuristic speaker labels as verbatim records or verified attribution.
- Introduce a correction path that records evidence and resolution without exposing unnecessary personal data.
- Check source terms and attribution needs before offering bulk transcript/document exports or automated downstream use.

## Delivery plan and measurable exit criteria

### First release gate

- Opinion FTS works in the Opinions Browser.
- Every public page has consistent data/source status and an appropriate report-error path.
- Case Explorer, Case Orders/3JX, and Oral Arguments expose the same lifecycle links/status.
- A clean setup runs all tests; CI runs unit and browser smoke checks.
- Current architecture/roadmap/contributing docs agree on pages, commands, data paths, and ownership.

### Second release gate

- Related cases/citations/comparison and bookmarks are visibly integrated.
- Profile, topic, and order research views have direct case links, meaningful filters, coverage notes, and exports.
- Derived artifacts have schema tests, refresh manifest metadata, and changelog entries.
- Mobile/keyboard/accessibility review has passed for the five highest-traffic surfaces.

### Third release gate

- Argument-to-disposition fact tables and explorer are live with confidence-aware, non-causal language.
- A versioned public research dataset and methodology/provenance documentation exist.
- The ingestion pipeline is observable, scheduled, and resilient to upstream format changes.

## Recommended next three implementation tickets

1. **Integrate FTS into Opinions Browser.** Small, clearly user-visible, and already supported by existing infrastructure.
2. **Add a reusable case lifecycle component.** It makes the existing opinions/orders/oral-arguments corpus feel like one product.
3. **Create a reliable test bootstrap and shared page shell.** This keeps subsequent work from further fragmenting the app.

These three tickets unlock the research experience, trust, and maintainability needed for every later improvement.
