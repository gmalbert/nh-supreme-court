# Casey 2026 Oral-Argument Transcription Execution Plan

> **For Hermes:** Complete the 2026 backlog before Granite transcript UI implementation.

**Goal:** Ensure every currently listed 2026 New Hampshire Supreme Court oral argument has a local Casey archive, downloaded audio, machine transcript, public markdown transcript, quality stats artifact, and Granite export.

**Architecture:** Treat the NH Supreme Court 2026 live-stream/archive page as the source manifest, stage every 2026 case into the Casey local archive, skip already-transcribed cases, and run the Casey pipeline (`download-audio` → `transcribe-audio` → `score-case` → `export-case`) for every missing case. Keep `small` as the default ASR model and preserve the option to rerun selected flagged cases with `turbo` later in copied temp workspaces.

**Tech Stack:** Casey profile Python script, `yt-dlp`, `ffmpeg/ffprobe`, `faster-whisper` (`small`, `int8`, CPU), local JSON/Markdown artifacts, Granite export JSON/CSV/Markdown/Text.

---

## Handoff review summary

Reviewed:
- `docs/plans/2026-06-14-casey-handoff-current-state.md`
- `docs/plans/2026-06-14-casey-transcript-statistics-plan.md`
- `docs/plans/2026-06-14-granite-oral-argument-linking-plan.md`
- `docs/plans/2026-06-13-casey-phase1.md`

Key confirmed facts:
- Archive root: `/Volumes/AI-Storage/nh-supreme-court-transcripts`
- Casey script: `/Users/greg/.hermes/profiles/casey/scripts/casey_phase1.py`
- Granite repo: `/Volumes/Users/gmalb/Downloads/nh-supreme-court`
- Default transcription model remains `small`
- Public transcript rendering remains grouped heuristic `Justice` / `Counsel`
- Existing verified 2026 transcripts before this run: 7 case folders in the archive
- Source-of-truth discovery page now resolves through `r.jina.ai` even though direct terminal fetches still 403

---

## Current execution target

The current 2026 live-stream page lists **47 oral arguments** spanning:
- `2026-01-08`
- `2026-01-27`
- `2026-02-10`
- `2026-02-12`
- `2026-03-10`
- `2026-03-19`
- `2026-03-26`
- `2026-04-07`
- `2026-04-09`
- `2026-04-21`
- `2026-05-05`
- `2026-05-12`
- `2026-05-19`

Backlog at plan time:
- 47 total listed 2026 arguments
- 7 already staged/transcribed/exported
- 40 still missing from the archive and must be processed

---

## Execution steps

### Task 1: Materialize a durable 2026 manifest
**Objective:** Save the 2026 source list as a Casey batch manifest.

Artifacts:
- Create `manifests/2026-live-stream-all.json`
- Preserve `source_page_url` as `https://www.courts.nh.gov/our-courts/supreme-court/oral-argument/live-stream#2026`
- Keep raw fetch snapshot at `/tmp/nh_live_stream_2026.md` for provenance during this run

Verification:
- Manifest count should equal 47.

### Task 2: Stage every 2026 case
**Objective:** Ensure all 47 cases have deterministic Casey archive folders.

Command shape:
```bash
/Users/greg/.hermes/profiles/casey/home/venv/bin/python \
  /Users/greg/.hermes/profiles/casey/scripts/casey_phase1.py \
  stage-manifest <manifest>
```

Verification:
- Case folders exist under `/Volumes/AI-Storage/nh-supreme-court-transcripts/2026/<date>/...`
- Existing 7 folders remain untouched apart from safe metadata preservation.

### Task 3: Batch process the backlog
**Objective:** Run the Casey pipeline on every case that does not already have transcript segments.

Per-case pipeline:
1. `download-audio`
2. `transcribe-audio --model small --language en --compute-type int8 --beam-size 5`
3. `score-case`
4. `export-case --repo-root /Volumes/Users/gmalb/Downloads/nh-supreme-court`

Behavior rules:
- Skip re-transcription for cases whose `raw/transcript_raw.json` already contains segments.
- Still allow score/export refresh where needed.
- Continue through the batch and log failures instead of aborting the whole run on the first error.
- Exit non-zero if any cases fail so the run is auditably incomplete.

### Task 4: Write batch status artifacts
**Objective:** Make long-running execution resumable and inspectable.

Artifacts:
- Batch log: `/Volumes/AI-Storage/nh-supreme-court-transcripts/logs/2026-full-batch.log`
- Batch summary JSON: `/Volumes/AI-Storage/nh-supreme-court-transcripts/logs/2026-full-batch-summary.json`

Verification:
- Summary records totals, skips, completed cases, and failures.

### Task 5: Verify completion
**Objective:** Confirm the archive and Granite exports reflect the full 2026 set.

Checks:
- 47 `metadata.json` files under the 2026 archive tree
- 47 per-case Granite oral-argument JSON exports
- aggregate `data/processed/oral_arguments.json` contains 47 2026 rows
- every successful case has:
  - `audio/oral_argument_audio.mp3`
  - `raw/transcript_raw.json` with non-empty `segments`
  - `public/transcript_public.md`
  - `public/transcript_stats.json`

---

## Implementation note after backlog completion

Once all 2026 transcripts exist locally and in Granite exports, the next implementation chat should wire `oral_arguments.json` into the Streamlit loaders and case pages using `case_number` as the join key.
