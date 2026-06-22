# Casey Phase 1 Prototype Plan

> **For Hermes:** Use this as the local-first implementation contract for Casey.

**Goal:** Stand up a dedicated Casey profile and a working local archive layout for NH Supreme Court oral-argument transcripts.

**Architecture:** Keep the archive on `/Volumes/AI-Storage/nh-supreme-court-transcripts` as the durable source of truth. In Phase 1, stage cases from a manifest into deterministic year/date/case folders with metadata, status, raw-transcript, and public-transcript placeholders. Delay automated discovery and transcription until the local fetch/download path is verified.

**Tech Stack:** Hermes profile-local scripts, Python 3.11, JSON/Markdown artifacts, later `yt-dlp` + `ffmpeg` + `faster-whisper` + optional diarization.

---

## What is done now

1. Created Hermes profile: `casey`
2. Created archive root and baseline folders:
   - `incoming/`
   - `manifests/`
   - `logs/`
   - `processed/`
3. Added profile-local script:
   - `~/.hermes/profiles/casey/scripts/casey_phase1.py`
4. Added sample manifest:
   - `~/.hermes/profiles/casey/scripts/sample_manifest.json`
5. Added archive README and this plan file.

## Filesystem contract

Per case:

```text
<archive_root>/<year>/<argument_date>/<docket>-<slug>/
  metadata.json
  status.json
  raw/transcript_raw.json
  public/transcript_public.md
```

## Immediate commands

Initialize layout:

```bash
python3 ~/.hermes/profiles/casey/scripts/casey_phase1.py init-layout
```

Stage the sample case:

```bash
python3 ~/.hermes/profiles/casey/scripts/casey_phase1.py stage-manifest \
  ~/.hermes/profiles/casey/scripts/sample_manifest.json
```

## Known blocker

The NH courts oral-argument page currently returns `HTTP 403 Access Denied` to simple terminal HTTP clients in this environment. Before Casey can auto-discover cases locally, we likely need one of:

1. Playwright/browser automation
2. an alternate public data endpoint
3. a manual/assisted manifest export step

## Phase 1 next implementation targets

1. Verify the staged archive structure against real cases
2. Add a manifest validator
3. Install and test `yt-dlp` against Vimeo case URLs
4. Add an audio download step (`audio/` folder)
5. Add a local transcription step
6. Add diarization as best-effort, non-blocking
7. Define the export shape for Granite State Appeals

## Streamlit integration direction

Granite State Appeals should eventually read exported app-ready artifacts derived from this archive, not write directly into the archive itself. That keeps the archive stable while the Streamlit schema evolves.
