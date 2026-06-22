# Casey / Granite Oral Arguments Handoff (Current State)

> **Purpose:** This file is the high-level handoff so a new Hermes chat can resume work quickly without relying on chat history.

**Last updated:** 2026-06-14

---

## What exists already

### Casey profile / local pipeline
- Hermes profile name: `casey`
- Main script: `/Users/greg/.hermes/profiles/casey/scripts/casey_phase1.py`
- Casey venv python: `/Users/greg/.hermes/profiles/casey/home/venv/bin/python`
- Archive root: `/Volumes/AI-Storage/nh-supreme-court-transcripts`

### Granite State Appeals repo
- Repo root: `/Volumes/Users/gmalb/Downloads/nh-supreme-court`
- Site: `https://nh-supreme-court.streamlit.app/`
- App stack: Python + Streamlit

---

## Key workflow decisions already made

### Storage / architecture
- Transcript artifacts should be stored locally under `/Volumes/AI-Storage/nh-supreme-court-transcripts`.
- The pipeline is local-first.
- Source audio comes from Vimeo links found on the NH Supreme Court oral-argument site.

### Public transcript formatting
- Public-facing transcripts should favor readability.
- Use heuristic `Justice` / `Counsel` labels when true diarization is unavailable.
- Merge consecutive same-speaker turns into a single paragraph in public-facing output.
- Do **not** claim true speaker identity when the underlying transcript lacks it.

### Model policy
- **Default transcription model: `small`**
- **Optional rerun model: `turbo`** when a case looks suspicious or important
- Do not overwrite archived baseline transcripts when comparing models; copy case folders to temp workspace first.

### Quality scoring policy
- There are no human-corrected transcripts right now.
- Casey uses **no-reference operational heuristics**, not true WER/CER.
- The scorer is for triage, review priority, and turbo-rerun decisions.

### Granite linking policy
- Canonical link key should be **`case_number` / docket**.
- `argument_date`, `case_name`, and `term_year` are secondary validation/filter fields, not the primary join key.

---

## Important docs created in the repo

### Planning docs
- `docs/plans/2026-06-14-casey-transcript-statistics-plan.md`
- `docs/plans/2026-06-14-granite-oral-argument-linking-plan.md`
- `docs/plans/2026-06-14-casey-handoff-current-state.md` ← this file

### Earlier Casey plan
- `docs/plans/2026-06-13-casey-phase1.md`

---

## Verified implementation state

### Casey script capabilities currently present
The script supports at least these commands:
- `stage-manifest`
- `download-audio`
- `transcribe-audio`
- `export-case`
- `score-case`

### Transcript stats artifact
Running `score-case` now writes a durable per-case stats file:
- `public/transcript_stats.json`

### Download fix already applied
`yt-dlp` audio extraction needed `ffmpeg` / `ffprobe` on this macOS setup.

Current resolved behavior:
- Casey prepends `/opt/homebrew/bin` to `PATH` during the download step
- this allows Vimeo audio extraction to succeed without manual shell setup each time

---

## Fresh verified case from this session

A fresh case was staged, downloaded, transcribed, scored, and exported:

- **Docket:** `2025-0240`
- **Case:** `Hologic, Inc. & a. v. Commissioner, New Hampshire Department of Revenue Administration & a.`
- **Argument date:** `2026-05-12`
- **Vimeo:** `https://vimeo.com/1191667448`

### Archive folder
`/Volumes/AI-Storage/nh-supreme-court-transcripts/2026/2026-05-12/2025-0240-hologic-inc-and-a-v-commissioner-new-hampshire-department-of-revenue-administration-and-a`

### Key artifacts
- Public transcript markdown:
  `.../public/transcript_public.md`
- Stats JSON:
  `.../public/transcript_stats.json`
- Granite export JSON:
  `/Volumes/Users/gmalb/Downloads/nh-supreme-court/data/processed/oral_arguments/2025-0240.json`
- Granite export text:
  `/Volumes/Users/gmalb/Downloads/nh-supreme-court/data/processed/oral_arguments/text/2025-0240.txt`
- Granite export markdown:
  `/Volumes/Users/gmalb/Downloads/nh-supreme-court/data/processed/oral_arguments/markdown/2025-0240.md`

### Verified scoring outcome for 2025-0240
- `operational_quality_score`: `84`
- `review_priority`: `medium`
- `recommendation`: `review-opening`
- `rerun_turbo_recommended`: `true`

Important observed signal:
- `opening_counsel_index`: `90`
- `opening_counsel_start_minutes`: `15.42`

Interpretation:
- the transcript is usable, but the opening is likely muddled
- this is exactly the sort of case that should be considered for turbo rerun / human review

---

## Current oral-argument export shape

Casey exports into Granite at:
- `data/processed/oral_arguments.json`
- `data/processed/oral_arguments.csv`
- `data/processed/oral_arguments/<docket>.json`
- `data/processed/oral_arguments/text/<docket>.txt`
- `data/processed/oral_arguments/markdown/<docket>.md`

A per-case oral-argument JSON currently includes fields such as:
- `case_number`
- `case_name`
- `argument_date`
- `term_year`
- `source_page_url`
- `vimeo_url`
- `audio_path`
- `duration_seconds`
- `segment_count`
- `language`
- `language_probability`
- `model`
- `compute_type`
- `beam_size`
- `has_speaker_labels`
- `speaker_label_status`
- `raw_transcript_json`
- `public_transcript_markdown`
- `granite_export_json`
- `granite_export_text`
- `granite_export_markdown`
- `transcript_text`
- `segments`

---

## Current Granite integration state

### Verified current behavior
Granite State Appeals currently routes case pages by `case_number`.

Relevant behavior observed in the codebase:
- links look like `case-explorer?case=<case_number>`
- `render_case_explorer()` reads `st.query_params.get("case", "")`
- the current app data loaders read:
  - `data/processed/opinions.csv`
  - `data/processed/all_opinions.json`

### Important gap
At the time of this handoff, no app code was found importing:
- `oral_arguments.json`
- `oral_arguments.csv`

So transcripts are being exported into the repo, but they are **not yet wired into the Streamlit UI**.

---

## Recommended next implementation steps

Choose one of these depending on the next chat goal.

### Option A: wire transcripts into Granite
1. Add transcript loaders in `utils/data_loader.py`
2. Load oral-argument records from `data/processed/oral_arguments.json` and/or CSV
3. Join transcript records to case pages by `case_number`
4. Render an “Oral Argument Transcript” section in the case explorer
5. Optionally surface quality/review metadata from `transcript_stats.json` or exported JSON

### Option B: improve Casey scoring / pipeline quality
1. Expand heuristics for opening-counsel detection
2. Add stronger repetition / restart-loop detection
3. Add model-comparison helpers for `small` vs `turbo`
4. Decide whether stats should also be embedded in Granite export JSON

### Option C: prepare for automation later
1. Build stable discovery for new NH oral-argument Vimeo entries
2. Build a profile-scoped cron workflow for Casey
3. Keep local-first storage and review checks before any automatic publishing to Granite

---

## Commands a new chat can run immediately

### Score an existing case
```bash
/Users/greg/.hermes/profiles/casey/home/venv/bin/python \
  /Users/greg/.hermes/profiles/casey/scripts/casey_phase1.py \
  score-case \
  /Volumes/AI-Storage/nh-supreme-court-transcripts/<year>/<date>/<case-dir>
```

### Re-export a case into Granite
```bash
/Users/greg/.hermes/profiles/casey/home/venv/bin/python \
  /Users/greg/.hermes/profiles/casey/scripts/casey_phase1.py \
  export-case \
  /Volumes/AI-Storage/nh-supreme-court-transcripts/<year>/<date>/<case-dir> \
  --repo-root /Volumes/Users/gmalb/Downloads/nh-supreme-court
```

---

## Bottom line for a future chat

A future Hermes chat should have enough written context to resume from the repo docs plus the Casey skill. The most important references are:
- `docs/plans/2026-06-14-casey-handoff-current-state.md`
- `docs/plans/2026-06-14-casey-transcript-statistics-plan.md`
- `docs/plans/2026-06-14-granite-oral-argument-linking-plan.md`

If the future task is implementation, start by reading those docs, then inspect:
- `/Users/greg/.hermes/profiles/casey/scripts/casey_phase1.py`
- `/Volumes/Users/gmalb/Downloads/nh-supreme-court/utils/data_loader.py`
- `/Volumes/Users/gmalb/Downloads/nh-supreme-court/cases.py`
