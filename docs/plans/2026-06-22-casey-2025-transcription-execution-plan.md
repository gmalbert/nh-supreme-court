# Casey 2025 Oral-Argument Transcription Execution Plan

> **For Hermes:** Complete the 2025 oral-argument backlog before Granite transcript UI implementation.

**Goal:** Ensure every currently discoverable 2025 New Hampshire Supreme Court oral argument has a local Casey archive, downloaded audio, machine transcript, public markdown transcript, quality stats artifact, and Granite export.

**Architecture:** Use a durable manifest under the local transcript archive, stage every manifest item through Casey, and run an idempotent batch that skips already-populated transcripts while still refreshing scoring and Granite exports. Keep `small` as the default ASR model; reserve `turbo` for later review reruns in copied temp folders only.

**Tech Stack:** Casey profile Python script, Vimeo/yt-dlp discovery and audio extraction, faster-whisper `small`/`int8`, local JSON/Markdown artifacts, Granite processed JSON/CSV/Text/Markdown exports.

---

## Context reviewed

- `docs/plans/2026-06-14-casey-handoff-current-state.md`
- `docs/plans/2026-06-14-casey-2026-transcription-execution-plan.md`
- Casey skill notes for batch discovery/resume and final audit
- Casey script commands: `stage-manifest`, `download-audio`, `transcribe-audio`, `score-case`, `export-case`

## Source/discovery notes

Direct terminal/browser access to the court page is Akamai-blocked from this environment. `web_extract` confirmed the official 2025 page contains 70 recorded arguments from January 14 through December 18, 2025. To avoid relying on truncated page summaries for execution, full video discovery uses the New Hampshire Judicial Branch Vimeo uploader listing and filters 2025 uploads whose titles are docket numbers.

Discovery artifact:

- Manifest: `/Volumes/AI-Storage/nh-supreme-court-transcripts/manifests/2025-live-stream-all.json`
- Source page: `https://www.courts.nh.gov/our-courts/supreme-court/oral-argument/live-stream/2025`
- Vimeo source: `https://vimeo.com/nhjb/videos`

The manifest contains 70 entries, matching the court-page count reported by `web_extract`. Known official case names were filled from existing Granite opinion data plus the court-page summary where available. Remaining entries use `Oral Argument <docket>` placeholders so transcription can proceed without blocking on metadata cleanup; those names can be corrected later without rerunning ASR.

## Execution target

- Total 2025 oral-argument recordings: 70
- Archive root: `/Volumes/AI-Storage/nh-supreme-court-transcripts`
- Granite repo: `/Volumes/Users/gmalb/Downloads/nh-supreme-court`
- Batch log: `/Volumes/AI-Storage/nh-supreme-court-transcripts/logs/2025-full-batch.log`
- Batch summary: `/Volumes/AI-Storage/nh-supreme-court-transcripts/logs/2025-full-batch-summary.json`

## Execution steps

### Task 1: Stage manifest

Run:

```bash
/Users/greg/.hermes/profiles/casey/home/venv/bin/python \
  /Users/greg/.hermes/profiles/casey/scripts/casey_phase1.py \
  stage-manifest \
  /Volumes/AI-Storage/nh-supreme-court-transcripts/manifests/2025-live-stream-all.json
```

Expected: 70 staged case folders under `/Volumes/AI-Storage/nh-supreme-court-transcripts/2025/<date>/...`.

### Task 2: Process every case idempotently

For each staged case:

1. If `raw/transcript_raw.json` already has non-empty `segments`, skip retranscription.
2. Otherwise run `download-audio`.
3. Run `transcribe-audio --model small --language en --compute-type int8 --beam-size 5`.
4. Run `score-case`.
5. Run `export-case --repo-root /Volumes/Users/gmalb/Downloads/nh-supreme-court`.
6. Continue on errors, record failures, and exit non-zero if any case fails.

### Task 3: Final audit

After the batch exits, verify:

- Manifest count is 70.
- Completed + failed equals 70.
- Failed count is 0 for a clean run.
- All manifest cases have matching archive `metadata.json`.
- Every successful case has:
  - `audio/oral_argument_audio.mp3`
  - `raw/transcript_raw.json` with non-empty `segments`
  - `public/transcript_public.md`
  - `public/transcript_stats.json`
  - Granite JSON/Text/Markdown exports
- Aggregate `data/processed/oral_arguments.json` contains 70 rows with `argument_date` beginning `2025-`.
- Report high/medium review-priority cases and turbo-rerun recommendations.

## Follow-up after transcription

Once the 2025 backlog is complete, Granite implementation can proceed using `case_number`/docket as the join key. If placeholder 2025 case names matter for UI polish, correct the affected `metadata.json` / manifest entries and rerun `export-case`; do not rerun transcription just to update names.
