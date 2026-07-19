# Oral Argument → Disposition Analytics Opportunities

**Purpose:** A product and data-analysis backlog for exploring how New Hampshire Supreme Court oral arguments become published opinions, case orders, 3JX orders, or remain unresolved in the local corpus. The emphasis is on slicing the same case lifecycle by lawyer, firm, subject, court term, and court behavior—without treating incomplete matching or a disposition label as a measure of advocacy quality.

## Executive recommendation

The strongest next product surface is an **Argument Outcomes Explorer**: one filterable dataset with one row per oral-argument docket (or explicitly grouped multi-docket matter), joined to the best available final disposition. It should power the existing Analysis page, Attorney Detail, Firm Detail, Topics, and a new case-lifecycle view rather than creating several disconnected dashboards.

Put the shared calculations in a reproducible build step and persist a research-ready fact table such as `data/processed/argument_dispositions.csv` (plus a data dictionary and refresh metadata). Keep page-specific charts as thin views of that table. This belongs in the app and the data pipeline, not only in a standalone Markdown report; this document belongs in `docs/` because it is a continuing product/data-design backlog.

## What the repository can already support

The current corpus has unusually good ingredients for a first version:

- Oral-argument records with docket, date, term, caption, video, duration, and transcript-derived speaking metrics.
- Docket crosswalks that accommodate aliases and combined dockets.
- Published opinion metadata, including dates, outcome, case type, topics, lower court, author, vote, dissents, statutory issues, and decision time.
- Case-order and 3JX-order inventories.
- Attorney, firm, side, and roster data, with confidence/review status in the newer counsel facts.
- Existing resolution logic that correctly preserves `multiple`, `needs_review`, and `unmatched` rather than silently forcing a match.

That means the first analytics should be framed as **observed published disposition among recorded arguments**, not as a claim about every appeal filed or every case fully resolved by the court.

## Build the canonical analysis layer first

### Proposed fact table: `argument_dispositions`

Grain: one argument record, with an explicit `matter_id` or grouping field for combined-docket arguments. Avoid multiplying rows merely because a matter has two lawyers, two topics, or multiple disposition records.

| Field group | Suggested fields |
| --- | --- |
| Identity | `argument_id`, `matter_id`, `case_number`, `docket_numbers`, canonical caption, combined-docket flag |
| Argument | argument date, term year, video URL, duration, transcript availability, segment count, counsel/justice speaking metrics |
| Disposition linkage | `resolution_type` (`opinion`, `case_order`, `3jx_order`, `multiple`, `needs_review`, `unmatched`), all matched record IDs, link confidence, match method, final/earliest disposition flag |
| Timing | disposition date, days argument→first disposition, days argument→final disposition, age bucket, pending flag |
| Opinion attributes | outcome, outcome-for side, case type, topics, author, vote string, unanimity, dissent/separate concurrence, lower-court fields, RSA/constitutional fields |
| Order attributes | order type, signed-by justices, 3JX flag/panel label, order text/summary availability |
| Participants | oral advocate, brief counsel, firm at time of argument, side, source, source confidence, review status |
| Data quality | source timestamps, confidence, candidate-match flag, missingness flags, corpus version |

Produce companion bridge tables rather than stuffing lists into one cell:

- `argument_participants`: one argument × attorney × role × side × firm-at-time-of-argument.
- `argument_topics`: one argument × topic.
- `argument_disposition_links`: one argument × disposition record, with link method/confidence and precedence.
- `argument_justice_metrics`: one argument × justice once individual justice speaker attribution is reliable.

### Rules that make the numbers defensible

1. **Separate an observed disposition from the court's ultimate procedural outcome.** An opinion, case order, and 3JX order are publication classes, not a common substantive outcome scale.
2. **Do not call a docket “no disposition” when it is simply unmatched.** Keep at least: pending/current term, PDF awaiting ingestion, historical corpus gap, needs review, and no located published disposition.
3. **Show the denominator beside every percentage.** Default to counts when a filtered cohort is small; suppress or flag lawyer/firm rates below a configurable threshold (for example, 10 resolved matters).
4. **Preserve multi-docket and multi-disposition cases.** Give the UI a matter-level default, with a record-level inspection mode for researchers.
5. **Use time-of-case firm affiliation.** A current firm directory should not rewrite historical representation.
6. **Distinguish oral advocate, brief counsel, scheduled-roster candidate, and inferred transcript speaker.** They answer different questions and carry different confidence.
7. **Never infer an advocate's win/loss from the caption alone.** Attribute a result only when appellant/appellee or party-side mapping is explicit and the outcome can be mapped safely.
8. **Label analysis as descriptive.** Lawyer experience, case mix, government representation, panel composition, and selection into oral argument are powerful confounders.

## High-value questions and views

### 1. The oral argument to disposition funnel

A top-level view should show, for any selected cohort, the progression:

`Recorded oral arguments → matched published disposition → opinion / case order / 3JX order → substantive outcome available → side-attributable outcome available`

Useful cuts:

- Term year and rolling 12-month cohorts.
- Case type, topic, lower-court type, statutory interpretation, and constitutional issue.
- Argument duration/complexity buckets.
- Attorney or firm, with a minimum-volume control.
- Argument date age buckets (0–90, 91–180, 181–365, 365+ days).

This becomes the honest starting point for every other chart: it makes clear whether an apparent difference reflects matching coverage, resolution speed, publication type, or outcome.

### 2. Disposition mix: opinions, case orders, and 3JX

For each cohort, show the percentage and count resolved through a full opinion, case order, 3JX order, or multiple published records.

Creative cuts:

- **Topic publication profile:** Which topics disproportionately produce full opinions versus orders or 3JX decisions?
- **Firm/attorney case-mix profile:** Does a firm’s apparent opinion rate persist after filtering to comparable case types and years?
- **Lower-court routing profile:** Which lower courts and appeal types most often lead to 3JX versus a signed opinion?
- **Precedent-production trend:** How has the share of argued matters producing a citable opinion changed by term?
- **Panel workload lens:** 3JX volume by year, case type, source court, and time from argument to issuance.

Present 3JX as a distinct disposition channel, not a lesser “win” or “loss.” It may be especially useful for understanding court capacity and procedural routing.

### 3. Timing and the court's decision calendar

Build an argument-to-disposition timing explorer using medians and percentile bands, not just averages.

Questions it can answer:

- Median and 25th/75th percentile days from argument to first/final disposition by year.
- Timing by disposition type, case type, topic, lower court, author, vote split, and opinion length.
- Whether dissents, separate concurrences, statutory interpretation, or constitutional issues correspond to longer elapsed time.
- “Fast lane” versus “long tail” topics: share resolved within 90/180/365 days.
- Seasonal pipeline: argument month versus issuance month, calendar-year end effects, and post-argument backlog snapshots.
- Firm/attorney **time-to-disposition profiles**, explicitly described as their case mix—not as their ability to speed the court.
- Outlier case timelines with visible source links, to support journalistic or academic research.

Recommended graphics: survival-style cumulative resolution curves, a calendar heatmap, a cohort heatmap (argument month × disposition month), and a sortable outlier table.

### 4. Outcome analysis—only where side attribution is sound

Once a resolved opinion can be joined to a reliable oral advocate and side, expose a carefully worded **observed outcome profile**, not a raw “win rate” by default.

Measures:

- Affirmed, reversed, vacated, remanded, mixed, dismissed, and other outcomes.
- Appellant-side success versus appellee-side success where `outcome_for` is reliable.
- Reversal/remand profile by attorney, firm, topic, case type, lower court, and year.
- Outcome mix before and after an attorney changes firms (descriptive career transition view).
- Advocate-versus-brief-counsel comparison, when both records are verified.
- Government versus private/represented party comparisons, stratified by criminal/civil/family and appeal type.

Essential UI language: “Among matched opinions with a verified advocate-side link,” followed by both the resolved denominator and the excluded/unattributed count. For orders and 3JX records, display disposition type and order type unless a separately reviewed substantive-outcome taxonomy supports a comparable result label.

### 5. Attorney and firm practice profiles

Extend current profiles from activity counts to a compact “practice fingerprint.”

- Matter volume, unique clients/party types where available, and active years.
- Share of work by case type, topic, lower court, appeal type, and disposition type.
- Side mix and opponent ecosystem (which offices/firms/attorneys they most often face).
- Typical argument duration, turn-taking/justice-question exposure, and case complexity—always compared with peers in the same case type.
- Opinion authors, voting patterns, and decision-time distribution for their matched matters.
- First appearance, peak years, rolling-three-year activity, and concentration/diversification of practice areas.
- “Comparable cohort” cards: e.g., outcomes/timing for attorney A versus all other advocates in criminal appeals, 2021–2025, excluding unresolved matters.
- Firm continuity: attorneys entering/leaving, share of firm arguments handled by the top one/two advocates, and succession when frequent advocates depart.

Avoid league-table-first design. Start with filterable profiles and allow ranking only after showing filters, counts, and a small-sample warning.

### 6. Topic and legal-issue intelligence

Topics become much more valuable when they connect oral argument, procedural outcome, and precedent.

- Arguments, matched dispositions, and opinion production by topic/year.
- Topic-specific median time to disposition and long-tail rate.
- Topic × outcome heatmap (where outcomes are comparable).
- Topic × lower-court matrix to see where legal issues originate.
- Topic × firm/attorney specialization, with minimum counts and overlap-aware display for multi-tag cases.
- RSA chapter and constitutional-provision trends: arguments, opinions, reversals, dissents, and citation growth.
- Emerging-topic detector: a topic’s recent volume versus its trailing baseline, with linked cases rather than an opaque score.
- “Precedent gap” finder: frequently argued topic/RSA combinations with few recent citable opinions.
- Citation follow-through: which argued topics generate opinions most cited in later NH decisions.

For multi-tag cases, offer both “cases may appear in more than one topic” counts and a fractional-allocation option; do not mix the two without a label.

### 7. Oral-argument behavior and the written result

The corpus has duration, segment, speaking-time, and pace data, so it can support carefully bounded exploratory analysis.

- Argument duration versus disposition type and time to decision.
- Justice speaking-time share, question/turn count, and counsel speaking pace by case type/topic and eventual disposition type.
- “Hot bench” profiles: cases in the top decile of justice interruptions or speaking share, with outcome/vote/timing distributions.
- Within-lawyer comparisons: an advocate’s typical speaking pattern against their own history, filtered to comparable case categories.
- Transcript text features: question words, statutory terms, uncertainty language, case-citation density, and issue-specific vocabulary.
- Argument/opinion semantic alignment: terms central at argument that appear (or do not appear) in the eventual opinion.
- Oral argument to authorial focus: justice-question themes against the final opinion’s cited statutes, holdings, and cited cases.

These should be labelled **exploratory correlations**. A high question count can mean a hard case, an engaged bench, transcript segmentation quirks, or a short exchange—not a predictive signal of who should win.

### 8. Justice, panel, and institutional views

Existing vote and authorship data can yield a court-behavior lens.

- Opinion authorship and time-to-decision by topic, case type, and argument cohort.
- Dissents/separate concurrences by topic, lower court, appeal type, and disposition timing.
- Argument cohort → later vote split: how often are argued matters unanimous versus divided?
- Recusal/not-participating patterns by subject area and party class (report counts, not speculative explanations).
- 3JX versus full-court disposition mix over time.
- Justice–attorney interaction metrics by topic/case type, once speaker attribution supports it; show exposure/opportunity (number of matched arguments) with every rate.
- Citation and precedent profile of opinions authored after oral argument: subsequent citations, statutory interpretation, and doctrinal topic.

Do not claim that a justice’s questions predict a vote without validating speaker attribution, controlling for obvious case differences, and treating the output as research—not decision support.

### 9. Network and ecosystem analysis

Network visuals can make recurrent litigation relationships visible.

- Attorney ↔ firm network across time; distinguish known historical firm from current directory enrichment.
- Attorney/firm ↔ topic bipartite graph to identify genuine specialization versus a single high-volume client.
- Opposing-counsel network: recurring matchups, government-office versus defender/private-firm patterns, and co-counsel clusters.
- Attorney/firm ↔ lower-court network, showing the pathways into Supreme Court review.
- Case citation network overlaid with topic and argued/not-argued status.
- “Institutional litigant” network for state agencies, municipalities, insurers, and repeat parties, if party normalization is added.

Default network views should use an interpretable threshold and an exportable edge table; a large hairball graph is rarely research-helpful.

### 10. Quality, coverage, and research operations dashboards

The data-quality story is itself useful and protects downstream conclusions.

- Join coverage by term, disposition type, topic, and attorney/firm.
- Count and aging of current-term pending cases, historical gaps, official PDFs awaiting ingestion, and human-review candidates.
- Counsel attribution confidence/review state by source and year.
- Docket alias/combined-docket match audit.
- Caption, transcript, topic, outcome, and speaker-attribution completeness scorecard.
- Refresh deltas: newly added arguments/dispositions, changed matches, and resolved review queue entries.
- Reproducibility panel: data refresh time, script/version, query filters, download/export timestamp.

This should be accessible to maintainers and summarized for users. It makes every public chart more credible.

## Suggested UI placement

| User need | Best location | Why |
| --- | --- | --- |
| Broad court-level funnel, timing, disposition mix, and coverage | Expand `pages/03_Analysis.py` with an “Arguments & Dispositions” workspace | The page already contains the core matching analysis and is the natural institutional dashboard. |
| A lawyer or firm's historical matter mix and observed outcomes | Extend `pages/09_Attorney_Detail.py` and `pages/10_Firm_Detail.py` | The user is already looking at a defined participant; comparisons can inherit their filters. |
| Topic-specific resolution and precedent profile | Extend `pages/04_Topics.py` | It keeps legal research organized around the legal issue rather than a generic chart gallery. |
| A single matter's procedural path | Case detail in `cases.py` / opinion page, with links to argument, order, 3JX, opinion, and citations | This is the best place for source-first verification. |
| Data health, join exceptions, and manually reviewable queues | Maintainer-only expander/page or documented build artifact | It is critical but should not dominate public research workflows. |
| Repeatable custom analysis | CSV/Parquet export plus a documented schema/API-like data contract | Researchers will want combinations the UI cannot anticipate. |

## A phased implementation path

### Phase 1 — trustworthy core (highest priority)

1. Create the canonical fact/bridge tables and data dictionary.
2. Persist every disposition link and match-confidence/method, including `multiple`, `needs_review`, and unresolved statuses.
3. Add a matter-level Argument Outcomes Explorer with year, case type, topic, disposition type, and age filters.
4. Ship the funnel, disposition-mix, and timing views with CSV export.
5. Add coverage/quality indicators to every relevant chart.

### Phase 2 — participant and topic profiles

1. Resolve attorney identities and historical firm affiliations where the source supports them.
2. Add case-mix and disposition profiles to attorney, firm, and topic pages.
3. Add conservative side-attributable outcome analysis for verified opinion/advocate joins.
4. Add comparable-cohort filters and minimum-denominator rules.

### Phase 3 — deeper court and transcript research

1. Add opinion author/vote/dissent/timing cross-tabs and 3JX routing analysis.
2. Add transcript-derived exploratory metrics and argument-to-opinion text alignment.
3. Add citation-network and precedent-follow-through views.
4. Add individual justice speaker attribution only after systematic validation.

### Phase 4 — advanced research capabilities

1. Event-study/cohort comparisons around rule, statutory, or personnel changes.
2. A documented downloadable research dataset with a changelog and stable identifiers.
3. Optional statistical notebooks: stratified estimates, confidence intervals, survival models, and sensitivity analyses for missing links.
4. A public methodology page explaining sources, definitions, exclusions, and known bias.

## Definition decisions to settle before publishing rates

- What counts as the final disposition when a docket has a case order and later opinion?
- Which order types are substantively comparable to an affirm/reverse outcome, and which should remain procedural labels?
- Does “firm” mean roster-listed firm, opinion appearance, manual metadata, or a separately verified historical affiliation?
- How should combined dockets be counted: one matter or one docket? Provide both but name the default.
- What minimum sample size, confidence interval, or suppression rule applies to attorney/firm outcome displays?
- Should topic reports use duplicated multi-label counts or fractional allocation?
- How far after argument should a matter be deemed “pending,” as opposed to a likely corpus gap?
- Which analyses may use heuristic transcript speaker labels, and which require reviewed attribution?

## Validation checklist for every new metric

- Rebuild deterministically from checked-in raw/processed inputs.
- Provide the numerator, denominator, exclusions, and date range in the chart/export.
- Test combined dockets, multiple matched dispositions, alias matches, missing dates, and unresolved records.
- Sample source PDFs/videos for every new join or classifier before surfacing a ranking.
- Compare roll-up totals with the existing resolution summary on the Analysis page.
- Ensure a chart's totals do not double-count multi-topic or multi-attorney matters unless it says so.
- Include confidence/missingness in exports, not only in a tooltip.
- Add tests alongside each new transformation; keep display calculations out of Streamlit page code where possible.

## Ideas deliberately deferred pending more data

- Causal claims that a particular lawyer, firm, question pattern, or justice interaction causes an outcome.
- Prediction of case results or votes from transcripts. This is vulnerable to small samples, confounding, and transcription/attribution error.
- Geography, client industry, demographic, financial-stakes, or amicus analyses without a sourced and reviewable collection process.
- Fine-grained individual-justice question analysis until speaker labels identify justices reliably rather than only the aggregate “justice” role.
- Cross-jurisdiction comparisons without normalizing court procedures and publication practices.

## First release: a concrete, useful cut

If only one feature is built next, make it this:

> **For any year/topic/case-type/attorney/firm cohort, show the number of recorded oral-argument matters; their matched published-disposition mix (opinion, case order, 3JX, multiple); resolution coverage; days to disposition; and, where verified, the opinion outcome by represented side. Every result links back to the argument and disposition source records.**

It is immediately useful, respects the corpus’s limits, and creates the shared data model that unlocks the more creative analyses above.
