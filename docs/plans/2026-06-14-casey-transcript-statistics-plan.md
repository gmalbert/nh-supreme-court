# Casey Transcript Statistics Plan

> **For future implementation:** this document captures the transcript-statistics concept separately from Granite import/linking.

**Goal:** Persist useful no-reference transcript statistics for each oral argument so Casey can score transcript quality, support review decisions, and surface operational metadata later in Granite State Appeals.

**Current verified state:**
- Casey script: `/Users/greg/.hermes/profiles/casey/scripts/casey_phase1.py`
- Local archive root: `/Volumes/AI-Storage/nh-supreme-court-transcripts`
- Per-case stats artifact now exists at `public/transcript_stats.json`
- Fresh verified example: docket `2025-0240`, argument date `2026-05-12`

---

## Scope

This plan is about **capturing and persisting transcript statistics** only.

It is not about:
- Streamlit UI rendering
- joining transcripts to opinions in Granite
- diarization or named-speaker identification

---

## Why this matters

The project does not have human-corrected reference transcripts, so classic accuracy metrics like WER/CER are unavailable. Casey therefore needs a **no-reference operational scoring layer** that helps answer:

- Does this transcript look healthy?
- Does the opening appear muddled?
- Should this case be reviewed manually?
- Should this case be rerun with `turbo`?
- Can we later expose confidence-like operational signals in Granite?

---

## Canonical artifact

Each staged/transcribed case should persist a case-local stats file:

`public/transcript_stats.json`

Example verified path:

`/Volumes/AI-Storage/nh-supreme-court-transcripts/2026/2026-05-12/2025-0240-hologic-inc-and-a-v-commissioner-new-hampshire-department-of-revenue-administration-and-a/public/transcript_stats.json`

This file should be treated as the canonical machine-readable stats artifact for the case.

---

## Statistics to capture

### Core transcript size and pacing
- `segment_count`
- `word_count`
- `character_count`
- `duration_seconds`
- `duration_minutes`
- `words_per_minute`
- `segments_per_minute`

### Opening quality / handoff heuristics
- `opening_counsel_index`
- `opening_counsel_start_seconds`
- `opening_counsel_start_minutes`

### Segment distribution
- `long_segment_count`
- `very_long_segment_count`
- `max_segment_words`
- `avg_words_per_segment`
- `median_words_per_segment`
- `p90_words_per_segment`
- `avg_chars_per_segment`
- `median_chars_per_segment`
- `long_segment_ratio`

### Repetition / loop heuristics
- `duplicate_segment_instances`
- `repeated_segment_ratio`
- `repeated_window_count`
- `repeated_window_density`

### Courtroom interaction signals
- `question_segment_count`
- `question_mark_count`
- `questions_per_minute`
- `exclamation_mark_count`

### Heuristic speaker-balance signals
- `speaker_guess_counts`
- `justice_guess_ratio`
- `counsel_guess_ratio`

### Model / inference metadata
- `model`
- `language`
- `language_probability`
- `beam_size`
- `compute_type`

### Operational assessment
- `operational_quality_score`
- `review_priority`
- `recommendation`
- `rerun_turbo_recommended`
- `warnings`

---

## Current observed example

Fresh verified case: `2025-0240`

Observed highlights:
- `operational_quality_score`: `84`
- `review_priority`: `medium`
- `recommendation`: `review-opening`
- `rerun_turbo_recommended`: `true`
- `opening_counsel_index`: `90`
- `opening_counsel_start_minutes`: `15.42`

Interpretation:
- the transcript is generally usable
- but the opening appears muddled and the first clear counsel-opening signal appears too late
- this is exactly the sort of case that should be flagged for review and possible turbo rerun

---

## Proposed implementation rules

1. Run the scorer after transcription completes.
2. Persist the result to `public/transcript_stats.json`.
3. Keep the raw transcript JSON separate from the stats artifact.
4. Treat the score as a **triage signal**, not a truth-level accuracy score.
5. Preserve warnings in plain language so they are readable without inspecting raw metrics.
6. If the opening signal is absent or implausibly late, prefer `rerun_turbo_recommended = true`.

---

## Recommended future uses

### Casey workflow
- auto-flag cases needing manual review
- decide whether to rerun a copied case with `turbo`
- track which heuristics most often correlate with bad openings

### Granite State Appeals
- optionally show an internal quality badge
- optionally filter transcripts by review priority
- optionally suppress or label low-confidence transcripts
- optionally expose pacing and duration metadata for readers/research

---

## Suggested future enhancements

- add named opening-counsel extraction when reliable
- detect abrupt restart loops more aggressively
- compare `small` vs `turbo` stats on copied case folders
- add historical dashboards for score distributions across terms/dates
- capture whether a transcript was later manually reviewed or rerun

---

## Implementation note

This concept should remain independent of Granite linking. The stats artifact should exist and be useful even before any Streamlit UI consumes it.
