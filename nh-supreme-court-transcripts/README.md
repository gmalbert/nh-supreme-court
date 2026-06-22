# NH Supreme Court Transcripts Archive

This directory is the local source-of-truth archive for the Casey transcription workflow.

The archive is intentionally **local-first**: source metadata, downloaded audio, raw Whisper output, public markdown, quality statistics, and batch logs all live here before anything is copied into the Granite State Appeals app.

## Current State

The 2026 oral-argument backlog has been processed.

Batch summary:

```text
manifest:        manifests/2026-live-stream-all.json
cases:           47
already present: 7
newly downloaded: 40
newly transcribed: 40
scored:          47
exported:        47
failures:        0
status:          complete
finished:        2026-06-15T03:57:25+00:00
```

Primary audit files:

```text
logs/2026-full-batch.log
logs/2026-full-batch-summary.json
```

The batch summary records successful Granite State Appeals exports to:

```text
/Volumes/Users/gmalb/Downloads/nh-supreme-court/data/processed/oral_arguments/
/Volumes/Users/gmalb/Downloads/nh-supreme-court/data/processed/oral_arguments/text/
/Volumes/Users/gmalb/Downloads/nh-supreme-court/data/processed/oral_arguments/markdown/
/Volumes/Users/gmalb/Downloads/nh-supreme-court/data/processed/oral_arguments.json
/Volumes/Users/gmalb/Downloads/nh-supreme-court/data/processed/oral_arguments.csv
```

Note: if `/Volumes/Users/gmalb/Downloads/nh-supreme-court` is not mounted in the current macOS/Hermes environment, re-counting those export files from here will fail even though the batch summary records successful writes from the original run.

## Intended Layout

```text
/Volumes/AI-Storage/nh-supreme-court-transcripts/
  README.md
  incoming/
  manifests/
    2026-live-stream-all.json
  logs/
    2026-full-batch.log
    2026-full-batch-summary.json
  processed/
  2026/
    2026-05-19/
      2024-0094-david-allen-individually-and-as-beneficiary-of-the-estate-of-priscilla-w-allen-v-peter-allen/
        metadata.json
        status.json
        source/
          <vimeo-id>.info.json
        audio/
          oral_argument_audio.mp3
        raw/
          transcript_raw.json
        public/
          transcript_public.md
          transcript_stats.json
```

## Artifact Contract

Each case folder should be treated as the durable archive record.

- `metadata.json` — canonical case-level record: docket, title, date, Vimeo/source URL, archive paths.
- `status.json` — operational state for download/transcription/rendering.
- `source/*.info.json` — `yt-dlp`/Vimeo metadata.
- `audio/oral_argument_audio.mp3` — normalized local audio source used for transcription.
- `raw/transcript_raw.json` — raw Whisper transcript with timestamped segments.
- `public/transcript_public.md` — readable public transcript.
- `public/transcript_stats.json` — no-reference quality score and review/rerun recommendations.

Raw transcript data should remain faithful to the ASR output. Public/exported views may add display-only speaker labels such as `Justice` and `Counsel`, but those labels are heuristic unless a future diarization step creates real speaker identities.

## Current Rendering Convention

Public transcripts should favor readability:

1. Preserve raw Whisper segments in `raw/transcript_raw.json`.
2. Build public markdown from normalized transcript text.
3. Use conservative heuristic `Justice` / `Counsel` display labels when true diarization is unavailable.
4. Merge consecutive same-display-speaker turns into a single paragraph.
5. Make clear in the website UI that speaker labels are inferred, not certified diarization.

Avoid publishing one paragraph per Whisper segment; it is difficult to read and makes oral arguments look choppy.

## Quality Triage

`public/transcript_stats.json` is a triage signal, not a human accuracy score. It flags likely problems such as late opening-counsel detection, repeated segments, or unusual segment shapes.

Known lower-score 2026 cases from the completed batch that should get extra review before being promoted as polished transcripts:

```text
2025-0344  score 63
2025-0416  score 69
2025-0273  score 69
2025-0030  score 75
2025-0185  score 75
2025-0028  score 75
2024-0465  score 75
2025-0133  score 75
2024-0407  score 75
2025-0019  score 75
```

Recommended policy:

- Publish all transcripts initially as machine-generated / beta.
- Surface the quality score or review status internally, not necessarily to public users.
- Prioritize the low-score cases above for manual spot checks or `turbo` comparison reruns.
- Do not replace `small` outputs globally with `turbo` outputs without a copied-workspace comparison, because `turbo` can improve phrasing on some cases but can also over-merge, drift, or hallucinate.

## Creating or Retrieving Transcript Statistics

Statistics are stored per transcript at:

```text
<case-folder>/public/transcript_stats.json
```

Example:

```text
/Volumes/AI-Storage/nh-supreme-court-transcripts/2026/2026-01-08/2024-0530-rjh-builders-llc-v-robert-thistle-and-a/public/transcript_stats.json
```

Each stats file includes:

- `operational_quality_score`
- `review_priority`
- `recommendation`
- `rerun_turbo_recommended`
- `warnings`
- `metrics.segment_count`
- `metrics.word_count`
- `metrics.duration_minutes`
- `metrics.words_per_minute`
- `metrics.opening_counsel_start_minutes`
- `metrics.long_segment_count`
- `metrics.repeated_segment_ratio`
- `metrics.question_mark_count`
- `metrics.speaker_guess_counts`
- `metrics.justice_guess_ratio`
- `metrics.counsel_guess_ratio`

### Retrieve an existing per-case stats file

Use the archive directly:

```bash
case_dir="/Volumes/AI-Storage/nh-supreme-court-transcripts/2026/<argument-date>/<case-folder>"
cat "$case_dir/public/transcript_stats.json"
```

Or inspect a compact subset:

```bash
python3 - <<'PY'
import json
from pathlib import Path
case_dir = Path('/Volumes/AI-Storage/nh-supreme-court-transcripts/2026/<argument-date>/<case-folder>')
stats = json.loads((case_dir / 'public' / 'transcript_stats.json').read_text())
print(stats['docket_number'], stats['operational_quality_score'], stats['review_priority'], stats['recommendation'])
print(stats['metrics']['word_count'], 'words')
print(stats['metrics']['duration_minutes'], 'minutes')
PY
```

### Retrieve all 2026 stats from the batch summary

The completed 2026 run also embedded every per-case score object in:

```text
logs/2026-full-batch-summary.json
```

That is the easiest source for a one-file audit table. Example extraction:

```bash
python3 - <<'PY'
import csv
import json
from pathlib import Path

summary = json.loads(Path('/Volumes/AI-Storage/nh-supreme-court-transcripts/logs/2026-full-batch-summary.json').read_text())
out = Path('/Volumes/AI-Storage/nh-supreme-court-transcripts/logs/2026-transcript-stats-index.csv')

rows = []
for case in summary['completed_cases']:
    score = case.get('score') or {}
    metrics = score.get('metrics') or {}
    rows.append({
        'docket_number': score.get('docket_number'),
        'case_name': score.get('case_name'),
        'argument_date': score.get('argument_date'),
        'model': score.get('model'),
        'operational_quality_score': score.get('operational_quality_score'),
        'review_priority': score.get('review_priority'),
        'recommendation': score.get('recommendation'),
        'rerun_turbo_recommended': score.get('rerun_turbo_recommended'),
        'word_count': metrics.get('word_count'),
        'duration_minutes': metrics.get('duration_minutes'),
        'words_per_minute': metrics.get('words_per_minute'),
        'segment_count': metrics.get('segment_count'),
        'justice_guess_ratio': metrics.get('justice_guess_ratio'),
        'counsel_guess_ratio': metrics.get('counsel_guess_ratio'),
        'stats_json_path': score.get('stats_json_path'),
    })

with out.open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

print(out)
PY
```

### Create or refresh stats for one transcript

Run `score-case` against a staged case folder:

```bash
/Users/greg/.hermes/profiles/casey/home/venv/bin/python \
  /Users/greg/.hermes/profiles/casey/scripts/casey_phase1.py \
  score-case \
  /Volumes/AI-Storage/nh-supreme-court-transcripts/2026/<argument-date>/<case-folder>
```

This reads the case metadata plus transcript artifacts, writes/overwrites:

```text
<case-folder>/public/transcript_stats.json
```

and prints the same score object to stdout.

### Create or refresh stats for a batch

For a full-year refresh, use the batch runner pattern rather than hand-running `score-case` dozens of times. The 2026 batch runner re-scored every case and wrote the combined audit to:

```text
logs/2026-full-batch-summary.json
```

If only stats changed and transcripts did not, the safe operation is:

1. iterate existing staged case folders,
2. run `score-case`,
3. run `export-case` so Granite State Appeals receives updated quality fields if the export schema includes them,
4. rebuild the Windows transfer payload.

### Stats in the Windows implementation

For Windows/Streamlit, prefer carrying stats in one of two ways:

1. **Best for app runtime:** include selected stats fields in `data/processed/oral_arguments.json` and/or each `data/processed/oral_arguments/<docket>.json` record during export.
2. **Best for audit/dev workflows:** copy a generated stats index such as `logs/2026-transcript-stats-index.csv` alongside the transfer bundle, or add it under `data/processed/` as `oral_argument_transcript_stats.csv`.

Do not make the deployed app read from absolute archive paths like `/Volumes/AI-Storage/...`. The archive path is a macOS/local-storage concern; the Windows app and deployed Streamlit app should use repo-relative files only.

## Recommended Granite State Appeals Implementation

The Streamlit app should treat transcripts as **processed data artifacts**, not as runtime-generated content.

Recommended app-side files:

```text
nh-supreme-court/
  data/
    processed/
      oral_arguments.json          # aggregate index for all transcript records
      oral_arguments.csv           # optional tabular index
      oral_arguments/
        <docket>.json              # structured transcript + metadata
        markdown/
          <docket>.md              # readable transcript body
        text/
          <docket>.txt             # plain text search/export fallback
```

Implementation approach:

1. Add a transcript availability field to the case/oral-argument data model.
   - `has_oral_argument_transcript: true|false`
   - `oral_argument_transcript_path`
   - `oral_argument_transcript_markdown_path`
   - `speaker_label_status: heuristic|complete|pending`
   - `transcript_quality_score`
   - `transcript_review_priority`

2. Load `data/processed/oral_arguments.json` once with Streamlit caching.
   - Use the aggregate JSON for search/listing/filtering.
   - Open the per-docket markdown only when rendering a selected case page.
   - Keep per-docket JSON available for richer segment/timestamp views later.

3. Join transcript availability to existing case rows by docket number.
   - Combined docket entries such as `2024-0722/2024-0723` need explicit handling.
   - Do not assume one docket string always maps to one case row.
   - Prefer a normalized join key list, e.g. `docket_numbers: ["2024-0722", "2024-0723"]`.

4. UI placement suggestion:
   - On case detail pages, add an "Oral Argument Transcript" section below the existing oral-argument/video link.
   - Show a concise disclosure: "Machine-generated transcript. Speaker labels are inferred for readability."
   - Render markdown by default.
   - Offer a download link for `.txt` or `.md`.
   - Optionally show timestamps/segments behind an expander later.

5. Search suggestion:
   - Start simple: search the aggregate transcript text or plain-text files locally.
   - For Streamlit, precompute a lightweight transcript index rather than scanning all markdown on every rerun.
   - Later upgrade to SQLite/FTS or a vector index only if simple full-text search becomes too slow.

6. Review workflow:
   - Add an internal/admin-only or developer-facing filter for `review_priority != "low"`.
   - Keep low-score cases visible but marked as machine-generated/beta.
   - Use the score to decide which cases to rerun or manually review, not to hide content by default.

## Moving Transcripts to Windows

Because implementation will happen on Windows, use a deliberate transfer step instead of relying on `/Volumes/...` paths existing there.

### Preferred transfer payload

For app implementation, the Windows repo needs the Granite export artifacts, not the whole archive with audio.

Copy this payload into the Windows checkout:

```text
data/processed/oral_arguments.json
data/processed/oral_arguments.csv
data/processed/oral_arguments/*.json
data/processed/oral_arguments/markdown/*.md
data/processed/oral_arguments/text/*.txt
```

That is enough for the website. It avoids moving large audio files and raw intermediate artifacts.

Keep this full archive on macOS/external storage as the source of truth:

```text
/Volumes/AI-Storage/nh-supreme-court-transcripts/
```

### If the macOS Granite export folder is available

From macOS, create a portable bundle from the Granite repo export directory:

```bash
cd /Volumes/Users/gmalb/Downloads/nh-supreme-court
zip -r /Volumes/AI-Storage/nh-supreme-court-transcripts/processed-oral-arguments-2026.zip \
  data/processed/oral_arguments.json \
  data/processed/oral_arguments.csv \
  data/processed/oral_arguments
```

Then copy `processed-oral-arguments-2026.zip` to Windows and extract it at the root of the Windows checkout of `nh-supreme-court`.

PowerShell extraction example:

```powershell
cd C:\path\to\nh-supreme-court
Expand-Archive -Force C:\path\to\processed-oral-arguments-2026.zip .
```

Verify on Windows:

```powershell
Get-ChildItem data\processed\oral_arguments -Filter *.json | Measure-Object
Test-Path data\processed\oral_arguments.json
Test-Path data\processed\oral_arguments.csv
```

Expected per the completed batch: 47 per-case JSON exports plus the aggregate files.

### If the macOS Granite export folder is not available

If `/Volumes/Users/gmalb/Downloads/nh-supreme-court` is not mounted, rebuild or copy from the archive instead:

1. Reconnect/mount the Granite repo volume on macOS, then rerun export from the archive; or
2. Build a transfer bundle from each case folder's `public/transcript_public.md`, `public/transcript_stats.json`, `metadata.json`, and `raw/transcript_raw.json`, then run a Windows-side import script to create the app's `data/processed/oral_arguments` layout.

Option 1 is cleaner because Casey's `export-case` already knows the app schema.

Re-export command pattern on macOS once the repo is mounted:

```bash
/Users/greg/.hermes/profiles/casey/home/venv/bin/python \
  /Users/greg/.hermes/profiles/casey/scripts/casey_phase1.py \
  export-case \
  /Volumes/AI-Storage/nh-supreme-court-transcripts/2026/<argument-date>/<case-dir> \
  --repo-root /Volumes/Users/gmalb/Downloads/nh-supreme-court
```

For all 2026 cases, prefer the existing batch/export runner rather than manually exporting one case at a time.

## Suggested Upload / Implementation Flow

Recommended end-to-end flow:

1. **On macOS / Casey environment**
   - Keep transcription generation here.
   - Treat `/Volumes/AI-Storage/nh-supreme-court-transcripts` as the durable archive.
   - Re-export into a mounted Granite repo whenever formatting/schema changes.

2. **Create a small website payload**
   - Package only `data/processed/oral_arguments*` artifacts.
   - Do not include `audio/`, `source/`, or full `raw/` archive data in the app unless needed for a future timestamped player.

3. **Move payload to Windows**
   - Copy the zip via external disk, SMB share, OneDrive/Dropbox, or Git LFS/release artifact.
   - Extract at the Windows repo root so paths remain relative and portable.

4. **Implement Streamlit integration on Windows**
   - Read local files from `data/processed/...` using `pathlib.Path`, never hard-coded `/Volumes/...` paths.
   - Add transcript availability joins by normalized docket number.
   - Add a transcript section to the case detail UI.
   - Add search/filter support after basic rendering works.

5. **Commit app code and processed text artifacts**
   - Plain text, markdown, JSON, and CSV are reasonable to commit if repository size remains acceptable.
   - Do not commit audio files.
   - If the transcript JSON/markdown payload becomes too large, store it as a release artifact or external data download and add a setup script.

6. **Deploy**
   - Streamlit deployment should read bundled relative paths.
   - Avoid depending on the macOS archive path at runtime.
   - Include a visible machine-transcript disclaimer.

## Future Refresh Workflow

When new oral arguments are added:

1. Update/create a manifest under `manifests/`.
2. Stage new cases.
3. Download/transcribe/score/export only missing cases.
4. Rebuild the website payload zip.
5. Copy/extract payload into the Windows repo.
6. Run app tests or a local Streamlit smoke test.
7. Commit/deploy updated processed artifacts.

## Discovery Note

Simple terminal HTTP requests to the NH courts oral-argument page previously returned HTTP 403 in this environment. The working discovery path for the 2026 batch used a browser-like/proxied extraction path and then preserved the canonical NH courts page URL in the manifest metadata.
