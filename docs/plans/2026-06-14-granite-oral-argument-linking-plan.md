# Granite Oral Argument Linking Plan

> **For future implementation:** this document captures how oral-argument transcripts should be imported into Granite State Appeals and linked to case pages.

**Goal:** Join Casey-generated oral-argument transcripts to Granite State Appeals in a stable, low-risk way that matches the app’s current routing model.

**Current verified state:**
- Granite repo root: `/Volumes/Users/gmalb/Downloads/nh-supreme-court`
- Streamlit case pages are keyed by `case_number`
- Current app data loaders read `opinions.csv` and `all_opinions.json`
- Casey exports oral-argument data to:
  - `data/processed/oral_arguments.json`
  - `data/processed/oral_arguments.csv`
  - `data/processed/oral_arguments/<docket>.json`
  - `data/processed/oral_arguments/text/<docket>.txt`
  - `data/processed/oral_arguments/markdown/<docket>.md`
- No current app code was found importing `oral_arguments.json` or `oral_arguments.csv`

---

## Core decision

**Primary link key: `case_number`**

This should be the canonical join key between:
- Casey transcript exports
- Granite opinion/case records
- Streamlit case-page routing

Why:
- Granite already routes case pages with `case-explorer?case=<case_number>`
- `render_case_explorer()` reads `st.query_params.get("case", "")`
- opinions data already uses `case_number`
- Casey transcript exports already use `case_number`

---

## What not to use as the primary key

### Not `term_year`
Reason: useful for filtering, but not unique enough.

### Not `argument_date`
Reason: useful for validation, but multiple cases can share the same date.

### Not `case_name`
Reason: naming variations, punctuation, abbreviations, and formatting differences make it too brittle.

---

## Recommended matching strategy

### Canonical join
- `transcript.case_number == opinion.case_number`

### Secondary validation checks
Use these to confirm or flag possible mismatches:
- `argument_date` vs `date_argued`
- normalized `case_name` similarity
- `term_year`

### Provenance fields to preserve
Keep these on the transcript record even though they are not join keys:
- `vimeo_url`
- `source_page_url`
- local archive/audio/transcript paths as internal metadata when helpful

---

## Recommended transcript record shape

Each oral-argument record imported into Granite should include at least:

- `case_number`
- `case_name`
- `argument_date`
- `term_year`
- `vimeo_url`
- `source_page_url`
- `duration_seconds`
- `segment_count`
- `model`
- `speaker_label_status`
- `transcript_text`
- `granite_export_markdown` or equivalent markdown content/path
- `operational_quality_score`
- `review_priority`
- `recommendation`
- `rerun_turbo_recommended`
- `metrics` / transcript statistics payload

---

## Data-flow recommendation

### Step 1: keep transcripts as a separate dataset
Treat oral arguments as their own dataset rather than trying to merge them directly into the master opinions CSV too early.

Recommended source files:
- `data/processed/oral_arguments.json`
- `data/processed/oral_arguments.csv`

### Step 2: load transcripts in a dedicated loader
Add a transcript loader parallel to the existing opinion loaders.

Likely future home:
- `utils/data_loader.py`

Potential functions:
- `load_oral_arguments()` → flat DataFrame
- `load_oral_arguments_json()` → raw JSON list
- `get_oral_argument(case_number)` → single transcript record or `None`

### Step 3: attach transcripts to case pages by `case_number`
When the case explorer is rendering a case, look up a transcript with the same `case_number`.

### Step 4: handle missing-opinion / transcript-first cases gracefully
Some transcripts may exist before a corresponding opinion is in the main opinions dataset.

Recommended behavior:
- keep them visible in a future oral-arguments view/index
- auto-attach them to case pages once the opinion dataset contains the same `case_number`

---

## Streamlit UI concept

### Minimum viable integration
On a case page, if a transcript exists for the case number:
- show an “Oral Argument Transcript” section
- link to Vimeo
- render transcript markdown or expandable text
- optionally show transcript metadata such as argument date, duration, model, and review priority

### Nice-to-have later
- badge for heuristic speaker labels
- badge for review priority / operational score
- link to local/exported markdown source if useful in dev/admin mode
- oral-arguments landing page with search/filter by date, year, or review status

---

## Validation rules

When joining transcript data to case pages:

1. Join by `case_number`.
2. If `argument_date` and `date_argued` both exist and differ, flag for review.
3. If normalized `case_name` differs materially, flag for review.
4. Do not fall back to `term_year` alone.
5. Do not silently match by fuzzy case name alone.

---

## Why this architecture is preferable

This keeps the system resilient because transcripts and opinions have different publication timelines:
- oral argument happens first
- transcript may be generated soon after
- opinion may appear much later

Using `case_number` as the stable cross-dataset identity lets Granite support all three states:
1. opinion only
2. transcript only
3. both opinion and transcript

---

## Implementation note

This concept should remain separate from transcript-statistics capture. Linking/import should consume transcript metadata and stats, but should not be responsible for producing them.
