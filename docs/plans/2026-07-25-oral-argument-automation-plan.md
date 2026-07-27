# Oral Argument Transcript Automation Plan

**Status:** Draft  
**Date:** 2026-07-25  
**Cost target:** $0 — everything runs on free GitHub Actions runners with local `faster-whisper`

---

## Current State

The oral argument transcript pipeline is a **two-environment split** with a fully manual handoff:

### macOS (Casey/Hermes) -- Manual
1. **Discovery** -- find new oral arguments on the NH court site (`courts.nh.gov/our-courts/supreme-court/oral-argument/live-stream/{year}`) using `r.jina.ai` or Playwright (direct requests get HTTP 403)
2. **Manifest creation** -- build `manifests/{year}-live-stream-all.json` mapping docket, case name, date, and Vimeo URL
3. **Stage** -- `casey_phase1.py stage-manifest` creates archive folder structure under `/Volumes/AI-Storage/nh-supreme-court-transcripts/`
4. **Download audio** -- `casey_phase1.py download-audio` uses `yt-dlp` + `ffmpeg` to pull MP3 from Vimeo
5. **Transcribe** -- `casey_phase1.py transcribe-audio` runs `faster-whisper` (`small` model, `int8`, beam size 5) for speech-to-text
6. **Score** -- `casey_phase1.py score-case` generates quality metrics
7. **Export** -- `casey_phase1.py export-case` copies artifacts into this repo at `data/processed/oral_arguments/`
8. **Commit** -- manual commit + push to trigger downstream stats regeneration

### GitHub Actions (Automated)
- Runs `refresh-data.yml` every Monday at 6 AM EST
- Scrapes opinions/case-orders, downloads PDFs, builds datasets
- Detects changes to `data/processed/oral_arguments*.json` and regenerates derived statistics (speaker, attorney, enhanced, interactions)
- Does **not** scrape oral argument dates, download Vimeo audio, or run transcription

### Completed Batches
- **2026**: 47 cases (complete)
- **2025**: 70 cases (complete)
- Earlier years: partially processed from PDF rosters, dates need verification

---

## Why This Runs at $0

**This is a public repo — GitHub Actions is unlimited and free.** No monthly minute cap applies.

| Runner resource | Available | What we need |
|----------------|-----------|-------------|
| CPU | 2 cores | `faster-whisper tiny` runs on 2 cores |
| RAM | 7 GB | `tiny` model ~75 MB, inference ~1.5 GB peak |
| Disk | 14 GB | Model cache ~100 MB, audio temp ~150 MB, artifacts ~5 MB |
| Timeout | 6 hours per job | ~8 min transcription time per argument (`tiny`, Linux CI) |

Real-world benchmarks: `faster-whisper tiny` on 2 CPU cores achieves roughly 3-5x real-time on Linux (CI runner) — slower on Windows due to I/O overhead. A 30-minute oral argument takes ~6-10 minutes to transcribe. At typical volume (< 5 new arguments per week), that's ~30-50 minutes of processing time per run — well within the 6-hour job timeout.

---

## Target Architecture

```
Weekly cron (early morning, low-traffic window)
    │
    ▼
GitHub Actions: ubuntu-latest (6h timeout, FREE)
    │
    ├── 1. DISCOVER ── Playwright scrapes court site for new cases
    │                   Compares against already-processed dockets
    │                   Output: _new_oral_arguments.json
    │
    ├── 2. DOWNLOAD ── yt-dlp + ffmpeg fetches audio from Vimeo
    │                   Temp storage in /tmp (deleted after transcription)
    │
    ├── 3. TRANSCRIBE ─ faster-whisper tiny (CPU, 75 MB model, ~3 min/case)
    │                   Output: raw transcript + public markdown
    │
    ├── 4. SCORE ────── No-reference quality heuristic (0-100)
    │                   If score < 50: queue for small-model re-transcription
    │
    ├── 5. EXPORT ──── Write per-case JSON, markdown, text to
    │                   data/processed/oral_arguments/
    │                   Rebuild oral_arguments.json index
    │
    ├── 6. STATS ────── Regenerate speaker, attorney, enhanced stats
    │
    ├── 7. VALIDATE ─── Refresh check, pytest, UI validation
    │
    └── 8. DEPLOY ──── Commit + push if changes detected
                       Open issue for any flagged/low-score cases
```

---

## Tiered Transcription Strategy

Rather than a single model for all cases, use a tiered approach that balances speed, quality, and zero cost:

### Tier 1 (default): `tiny` model
- Model size: 75 MB
- Speed: ~3-5x real-time on Linux CI (~6-10 min per 30-min argument)
- Quality: decent for clean NH court audio (formal legal speech, single language)
- Runs every week for all new cases

### Tier 2 (automatic upgrade): `small` model
- Model size: 466 MB
- Speed: ~2-3x real-time on Linux CI (~10-15 min per 30-min argument)
- Quality: significantly better accuracy, fewer hallucinations
- Triggered automatically when `tiny` produces a quality score < 50

### Tier 3 (manual review only): `turbo` model
- Model size: 1.5 GB
- Speed: ~1-2x real-time on CPU (~15-30 min per 30-min argument)
- Quality: near-API quality
- Run manually on the Mac for cases flagged by the scorer with `rerun_turbo_recommended: true`

```python
# scripts/casey/config.py
TRANSCRIPTION_TIERS = {
    "tiny": {
        "model": "tiny",
        "compute_type": "int8",
        "beam_size": 3,
        "est_minutes_per_30min_arg": 8,
        "trigger": "default",
    },
    "small": {
        "model": "small",
        "compute_type": "int8",
        "beam_size": 5,
        "est_minutes_per_30min_arg": 12,
        "trigger": "quality_score_below_50",
    },
    "turbo": {
        "model": "turbo",
        "compute_type": "float16",
        "beam_size": 5,
        "est_minutes_per_30min_arg": 20,
        "trigger": "manual_on_mac_only",
    },
}
```

### Caching Whisper models in CI

First-run model download adds ~30 seconds (tiny) to ~2 minutes (small). Cache the HuggingFace model directory in GitHub Actions to avoid re-downloading:

```yaml
- name: Cache faster-whisper models
  uses: actions/cache@v4
  with:
    path: ~/.cache/huggingface
    key: whisper-models-${{ runner.os }}-v1
```

---

## Phase 1: Port Casey to the Repo (1-2 sessions)

**Goal:** Make the transcription pipeline self-contained within this repository so it can run without Hermes/macOS paths.

### 1.1 Create `scripts/casey/` package

Move the Casey logic from `~/.hermes/profiles/casey/scripts/casey_phase1.py` into this repo as a package:

```
scripts/casey/
├── __init__.py
├── cli.py              # Subcommand router (discover, download, transcribe, score, export)
├── discover.py         # Court-site scraper (Playwright-based)
├── download.py         # Vimeo audio downloader (yt-dlp + ffmpeg)
├── transcribe.py       # faster-whisper runner with tiered model selection
├── score.py            # Quality scoring (0-100)
├── export.py           # Granite repo artifact export
├── manifest.py         # Manifest read/write helpers
├── archive.py          # Archive layout utilities
├── contracts.py        # Data schemas (TypedDicts / dataclasses)
└── config.py           # Paths, model defaults, tier configurations
```

### 1.2 Remove macOS hard-coding

- Replace `/Volumes/AI-Storage/nh-supreme-court-transcripts/` with a path resolved relative to the repo root or an env var (`CASEY_ARCHIVE_ROOT`)
- Replace `/Users/greg/.hermes/...` venv paths with standard `pip` dependencies
- The archive root defaults to `nh-supreme-court-transcripts/` within the repo for CI, overridable for local Mac use

### 1.3 Add dependencies to `requirements.txt`

```
faster-whisper>=1.0.0
yt-dlp>=2024.0.0
```

`ffmpeg` is already available on `ubuntu-latest` GitHub runners. No additional system packages needed.

### 1.4 Implement CLI

```bash
# Discovery
python -m scripts.casey.cli discover --year 2026 --output manifests/2026-new.json

# Download a single case
python -m scripts.casey.cli download --docket 2026-0123 --vimeo-url https://vimeo.com/...

# Transcribe (defaults to tiny; --tier small for upgrade)
python -m scripts.casey.cli transcribe --docket 2026-0123
python -m scripts.casey.cli transcribe --docket 2026-0123 --tier small

# Score
python -m scripts.casey.cli score --docket 2026-0123

# Export to repo
python -m scripts.casey.cli export --docket 2026-0123

# Full pipeline for a case (discover → download → transcribe → score → export)
python -m scripts.casey.cli process --docket 2026-0123 --vimeo-url ...
```

### 1.5 Verify idempotency

Every subcommand must be safe to re-run:
- `download` -- skip if `audio/oral_argument_audio.mp3` exists and is non-zero
- `transcribe` -- skip if `raw/transcript_raw.json` exists and segment count > 0; if a higher tier is requested (e.g., `small` after `tiny`), re-transcribe and overwrite
- `score` -- skip if `public/transcript_stats.json` exists (unless transcript was regenerated)
- `export` -- overwrite Granite artifacts (stateless, git will diff)

---

## Phase 2: Discovery Automation (1 session)

**Goal:** Automatically find new oral arguments posted to the NH court site.

### 2.1 Playwright scraper

The court site (`courts.nh.gov/our-courts/supreme-court/oral-argument/live-stream/{year}`) returns HTTP 403 to simple HTTP clients. Playwright with Chromium already works in the existing workflow.

Script: `scripts/casey/discover.py`

- Navigate to each target year page (current year + one prior by default)
- Extract `<table>` rows: date from first `<td>`, docket regex from second `<td>`, name from remaining cells
- Extract Vimeo iframe `src` URLs from the page
- Compare extracted dockets against `data/processed/oral_arguments.json` to find new cases
- Output new-cases manifest JSON

### 2.2 Vimeo fallback for missing URLs

If the court page doesn't expose Vimeo IDs directly:

- Query `https://vimeo.com/nhjb/videos` filtered by upload date
- Match by docket number appearing in video title
- This is already the fallback used for the 2025 batch

### 2.3 Manifest format

```json
[
  {
    "docket": "2026-0123",
    "case_name": "State v. Smith",
    "argument_date": "2026-07-15",
    "vimeo_url": "https://vimeo.com/123456789",
    "year": 2026
  }
]
```

---

## Phase 3: CI Workflow Integration (1-2 sessions)

**Goal:** Wire the pipeline into the existing `refresh-data.yml` workflow.

### 3.1 Workflow placement

Add oral argument processing as a step in `refresh-data.yml`, placed after opinion/case-order scraping and before statistics regeneration. This ensures new transcripts feed into stats.

### 3.2 New workflow step

```yaml
- name: Discover and process new oral arguments
  run: |
    # Discover new cases
    CURRENT_YEAR=$(date +%Y)
    PRIOR_YEAR=$((CURRENT_YEAR - 1))
    python -m scripts.casey.cli discover \
      --year "$CURRENT_YEAR" --year "$PRIOR_YEAR" \
      --output data/processed/_new_oral_arguments.json

    # Process each new case (tier 1: tiny model, fast and free)
    python -m scripts.casey.cli process-manifest \
      --manifest data/processed/_new_oral_arguments.json \
      --archive-root nh-supreme-court-transcripts \
      --tier tiny

    # Check quality scores; re-transcribe low-scoring cases with small model
    python -m scripts.casey.cli process-manifest \
      --manifest data/processed/_new_oral_arguments.json \
      --archive-root nh-supreme-court-transcripts \
      --tier small --only-below-score 50

    # Build/rebuild indexes
    python scripts/build_oral_argument_index.py
    python scripts/build_transcript_index.py
```

### 3.3 Model caching step

```yaml
- name: Cache faster-whisper models
  uses: actions/cache@v4
  with:
    path: ~/.cache/huggingface
    key: whisper-models-${{ runner.os }}-v2
```

### 3.4 Timeout safety

`faster-whisper tiny` achieves roughly 3-5x real-time on Linux (2 CPU cores), so a 30-minute oral argument takes ~6-10 minutes to transcribe. A weekly batch of < 5 new cases uses ~30-50 minutes of the 6-hour job budget. If the scorer triggers `small` re-transcription for all 5 (~50-75 additional minutes), it's still well within limits. GitHub Actions is free and unlimited for public repos.

1. Process one case at a time, commit after each — partial progress is preserved
2. The `tiny` tier completes all cases first (always fast)
3. `small` re-transcription is a separate step that can be skipped on timeout without losing the `tiny` results

### 3.5 Audio storage

Downloaded MP3 files (~50-150 MB each) are stored in `/tmp` during transcription and deleted immediately after. If re-transcription is needed, the audio is re-downloaded from Vimeo (yt-dlp caches by default, so this is fast on re-run within the same workflow).

No persistent audio storage needed — zero infrastructure cost.

### 3.6 Workflow diagram

```
┌─ refresh-data.yml (Monday 6 AM, ubuntu-latest, FREE) ─────────────────┐
│                                                                         │
│  Scrape opinions & case orders (Playwright)                            │
│  Download/parse PDFs, build datasets                                   │
│                                                                         │
│  ┌─ NEW: Oral Argument Pipeline ($0) ──────────────────────────────┐   │
│  │                                                                   │   │
│  │  Cache restore: faster-whisper models (~/.cache/huggingface)     │   │
│  │                                                                   │   │
│  │  1. Discover new cases (Playwright scrapes court site)           │   │
│  │     └─ Output: _new_oral_arguments.json                          │   │
│  │                                                                   │   │
│  │  2. For each new case:                                           │   │
│  │     ├─ download: yt-dlp Vimeo → /tmp/audio.mp3                   │   │
│  │     ├─ transcribe: faster-whisper tiny (75 MB, ~3 min)           │   │
│  │     ├─ score: quality heuristic → 0-100                          │   │
│  │     ├─ if score < 50: re-transcribe with small (466 MB, ~10 min) │   │
│  │     └─ export: → data/processed/oral_arguments/                  │   │
│  │     └─ cleanup: rm /tmp/audio.mp3                                │   │
│  │                                                                   │   │
│  │  3. Rebuild indexes                                              │   │
│  │     ├─ build_oral_argument_index.py                              │   │
│  │     └─ build_transcript_index.py                                 │   │
│  │                                                                   │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Regenerate oral argument stats (speaker, attorney, enhanced)           │
│  Validate (pytest + UI)                                                 │
│  Commit & push if changes detected                                      │
│  Open issue for cases flagged turbo_recommended                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 4: Date Correction Automation (1 session)

**Goal:** Eliminate placeholder `-10-01` dates by scraping actual argument dates.

### 4.1 Integrate date scraping

`scripts/scrape_oral_argument_dates_playwright.py` already works. Run it after oral argument processing:

```yaml
- name: Correct oral argument dates
  run: |
    xvfb-run -a python scripts/scrape_oral_argument_dates_playwright.py --all
    python scripts/build_oral_argument_index.py
```

---

## Phase 5: Monitoring & Alerting (1 session)

### 5.1 Quality gates

After processing, check:
- No case scored below 40 (`review_priority == "high"`)
- No case has zero segments (silent audio, download failure)
- No downstream stat regeneration fails
- Git diff shows expected changes only

### 5.2 Issue creation

Cases flagged with `review_priority: high` or `rerun_turbo_recommended: true` → auto-create a GitHub issue:

```yaml
- name: Create issue for flagged transcripts
  if: steps.quality_check.outputs.flagged != ''
  run: |
    gh issue create \
      --title "Low-quality transcript(s) need manual re-transcription" \
      --body "${{ steps.quality_check.outputs.flagged }}" \
      --label "oral-arguments,needs-review"
```

These flagged cases can then be re-transcribed manually on the Mac with `--tier turbo`.

### 5.3 Weekly summary

A step at the end of the workflow posts a summary comment on a tracking issue:

```
## Oral Argument Processing -- Week of 2026-07-28
- New arguments discovered: 3
- Transcribed (tier 1 / tiny): 3
- Upgraded to small (score < 50): 0
- Average quality score: 78
- Flagged for turbo re-run: 0
- Dates corrected: 0
- Runner minutes used: ~40 (public repo, unlimited)
```

---

## Phase 6: Local Mac Sync (Optional)

**Goal:** Keep the local Mac archive in sync for manual re-transcription of flagged cases.

### 6.1 Pull-based sync

The Mac-side archive at `/Volumes/AI-Storage/` can be synced by pulling the repo and running:

```bash
python -m scripts.casey.cli sync-from-repo \
  --archive-root /Volumes/AI-Storage/nh-supreme-court-transcripts
```

### 6.2 Manual re-transcription

For cases that the scorer flags for `turbo` re-transcription:

```bash
# Download audio from Vimeo (or use cached archive copy)
python -m scripts.casey.cli download --docket 2026-0123 --vimeo-url ...

# Re-transcribe with turbo model (much better on Mac with GPU)
python -m scripts.casey.cli transcribe --docket 2026-0123 --tier turbo

# Re-score and re-export
python -m scripts.casey.cli score --docket 2026-0123
python -m scripts.casey.cli export --docket 2026-0123
```

---

## Implementation Order

| Phase | Task | Priority | Effort | Depends On |
|-------|------|----------|--------|------------|
| 1.1 | Create `scripts/casey/` package | P0 | 1 session | -- |
| 1.2 | Remove macOS hard-coding | P0 | 1 session | 1.1 |
| 1.3 | Add deps (`faster-whisper`, `yt-dlp`) | P0 | < 1 session | -- |
| 1.4 | Implement CLI (discover, download, transcribe, score, export) | P0 | 1 session | 1.1, 1.2 |
| 1.5 | Verify idempotency | P0 | < 1 session | 1.4 |
| 2.1 | Playwright scraper for court site | P0 | 1 session | 1.1 |
| 2.2 | Vimeo fallback discovery | P1 | bundled | 2.1 |
| 3.1 | CI workflow integration | P0 | 1 session | 1.4, 2.1 |
| 3.2 | Whisper model caching in Actions | P0 | < 1 session | 3.1 |
| 3.3 | Tiered transcription (tiny → small upgrade) | P1 | < 1 session | 1.4 |
| 4.1 | Date correction in workflow | P1 | < 1 session | 3.1 |
| 5.1 | Quality gates + issue creation | P1 | < 1 session | 3.1 |
| 5.2 | Weekly summary comment | P2 | < 1 session | 5.1 |
| 6.1 | Pull-based Mac sync | P3 | < 1 session | 1.4 |

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Court site changes HTML structure | Medium | Discover step fails | Playwright resilient to JS-heavy pages; fallback to Vimeo scraper |
| `tiny` model quality below threshold | Low | Cases need small re-run | Automatic upgrade path in tiered strategy |
| GitHub Actions timeout (20+ backlogged cases all need `small` model) | Low | Partial progress | Commit after each case; tiny model always completes first |
| Vimeo URLs expire or go private | Low | Can't download audio | Re-download from Vimeo on re-run (cases stay available for months) |
| `faster-whisper` model download slow on first run | Medium | 30s-2min first-run delay | GitHub Actions cache (`actions/cache@v4`), hits on subsequent runs |
| `ffmpeg` not available on runner | Very low | Download fails | `ubuntu-latest` has ffmpeg preinstalled; verify in workflow step |
| Rate limiting from court site or Vimeo | Low | Discovery/download blocked | Delays between requests; yt-dlp handles retries |

---

## Success Criteria

1. **$0 cost** — everything runs on free GitHub Actions runners with local `faster-whisper`; no paid APIs
2. **No manual steps** — a new oral argument posted to the court site is transcribed and available in the app within one week
3. **Fault-tolerant** — a single failed transcription does not block the rest of the pipeline; partial commits preserve progress
4. **Observable** — quality scores and flagged cases are surfaced via GitHub issues
5. **Idempotent** — re-running the pipeline does not duplicate or corrupt existing data
6. **Upgradable** — `turbo` model available for manual re-transcription of flagged cases on the Mac, without blocking the automated pipeline
