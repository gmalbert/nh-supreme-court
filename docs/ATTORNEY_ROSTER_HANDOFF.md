# Attorney Roster Attribution Handoff

**Purpose:** Preserve the findings and implementation decisions from the attorney-roster investigation so another model can continue the work without relying on conversation history.

## Core Finding

Transcript `metadata.json` files are not reliable enough to be the primary source for attorney attribution. They contain wrong case identities, stale counsel, omitted counsel, synthetic names, and incorrect side assignments.

The saved New Hampshire Supreme Court annual live-stream archive PDFs are the best source for oral-argument participation. They list the docket, parties, counsel, side, allotted time, and video link.

Official opinions and orders remain necessary for counsel who appeared only on briefs, institutional counsel, and final published appearance language.

## Source Hierarchy

Use the following hierarchy:

1. **Annual live-stream/archive PDFs:** authoritative for attorneys who argued orally.
2. **Official opinions and orders:** authoritative for brief counsel, institutional counsel, and formal published appearances.
3. **Transcript metadata:** supporting evidence and fallback only; never override a conflicting court source automatically.
4. **Manual review:** required when sources conflict, names are ambiguous, or PDF parsing confidence is low.

The archived PDFs are stored outside the Git repository at:

`/Volumes/AI-Storage/nh-supreme-court-transcripts/enrichment/user-pages/2015.pdf` through `2026.pdf`

The local transcript archive is the durable source of truth:

`/Volumes/AI-Storage/nh-supreme-court-transcripts`

## Three Distinct Attribution Types

Do not collapse these into one attorney roster:

- `oral_advocate`: actually presented oral argument.
- `brief_counsel`: listed on the brief or memorandum but did not necessarily argue.
- `institutional_counsel`: attorney general, solicitor general, county counsel, or similar institutional appearance.

Examples:

- `2013-0554`: Jason A. Casey argued for the State; Stephen D. Fuller was on the brief.
- `2014-0465`: Talesha L. Caynon argued for the defendant; Andru H. Volinsky was also on the brief.
- `2014-0458`: Paul M. Monzione argued for the petitioner; Stephan T. Nix was on the brief.
- `2020-0595`: Gregory M. Albert and Michael D. Ramsdell appeared on the briefs, but the case was submitted without oral argument. It should not be added to oral-argument profile counts.

Attorney profiles currently represent oral arguments. Brief-only counsel should be displayed on case pages and should only be added to a separate brief-counsel profile/category in a future expansion.

## Current Implementation

### PDF roster generation

`scripts/build_pdf_attorney_roster_overrides.py` reads the saved annual PDFs and generates:

`data/pdf_attorney_roster_overrides.json`

The current generated file contains the reviewed 100-case sample. It captures names, side, firm where available, and source provenance.

The parser handles:

- Parenthesized names such as `(Michele E. Kenney)`.
- Multiple names joined by `and`.
- Plain-text counsel immediately above `(15 min.)`.
- Suffixes such as `IV` and `Jr.`.
- Multiple attorneys on one side.
- Common non-attorney party-name false positives.

The parser uses `pdftotext -raw`. It first checks the system PATH and then the known bundled Poppler path used in this environment.

### Statistics generation

`scripts/extract_attorney_stats.py` loads the PDF roster overrides with precedence over the older manual case overrides and transcript metadata.

The generated statistics file is:

`data/processed/oral_arguments_attorney_stats.json`

The current pipeline preserves the existing name canonicalization map in `data/attorney_name_map.json`.

### Reproduction commands

Regenerate the 100-case PDF roster:

```bash
python3 scripts/build_pdf_attorney_roster_overrides.py --sample-size 100
```

Regenerate attorney statistics:

```bash
python3 scripts/extract_attorney_stats.py
```

Validate syntax and JSON:

```bash
python3 -m py_compile scripts/build_pdf_attorney_roster_overrides.py scripts/extract_attorney_stats.py
jq empty data/pdf_attorney_roster_overrides.json data/processed/oral_arguments_attorney_stats.json
git diff --check
```

## Verified Cases

### `2013-0554`

PDF oral roster:

- Jason A. Casey, State
- Christopher M. Johnson, defendant

Official opinion additionally lists Stephen D. Fuller on the State brief.

### `2013-0833`

PDF oral roster:

- Nicholas P. Cort, State
- John L. Riff, IV, defendant

The PDF printed Riff as plain text with a suffix. The parser initially missed him; this is fixed.

### `2014-0028`

PDF oral roster:

- John S. Krupski, petitioner
- Carolyn M. Kirby, respondent

Transcript metadata incorrectly listed Nicholas P. Cort and Robert J. Moses for an unrelated case identity. The official opinion confirms Krupski and Kirby.

### `2014-0081`

PDF oral roster:

- Bradford Dutton, self-represented
- Christopher J. Poulin, Town of Salem

The metadata incorrectly listed Elizabeth C. Woodcock and Sarah E. Newhall for “Beausoleil.” Only Poulin is an attorney in the oral roster.

### `2014-0458`

PDF oral roster:

- Paul M. Monzione, petitioner
- Rebecca L. Woodard, respondent

The official opinion additionally lists Stephan T. Nix as brief counsel for the petitioner.

### `2014-0465`

PDF oral roster:

- Michele E. Kenney, petitioner
- Talesha L. Caynon, respondent

The official opinion additionally lists Andru H. Volinsky as brief counsel for the respondent. Caynon also argued orally.

### `2019-0280`

PDF and official opinion agree on:

- Gregory M. Albert, State
- Michael D. Ramsdell, defendant

This case was manually corrected in `data/case_attorney_overrides.json` before the PDF sample work.

## Important Data Distinction

The 100-case PDF correction is currently an oral-advocate correction, not a complete all-counsel correction. It should not be interpreted as proof that the case had only those attorneys in every procedural role.

For a complete case counsel display, parse official opinion/order appearance blocks separately and preserve labels such as:

- `on the brief`
- `on the memorandum`
- `orally`
- `for the State`
- `for the petitioner`
- `for the respondent`

The UI should make the role visible rather than presenting all names as equivalent participants.

## Known Historical Issue

`docs/oral_arguments_date_fix_RESOLVED.md` claims that all 1,071 oral-argument dates were corrected and that zero October 1 placeholders remained. The current `data/processed/oral_arguments.json` was later restored by a cloud-deployment data commit and still contains placeholder dates. Do not assume the date-fix document reflects the current data snapshot; verify the actual JSON before relying on it.

## Remaining Work

1. Expand the PDF roster reconciliation beyond the reviewed 100-case sample.
2. Add a side-aware, confidence-scored representation for oral advocates and brief counsel.
3. Parse official opinion/order appearance blocks into a separate counsel dataset.
4. Add regression tests for plain-text names, suffixes, multiple counsel, self-represented parties, consolidated cases, and brief-only counsel.
5. Review cases where PDF names and official opinion names disagree.
6. Update the case page to show oral advocates and brief counsel in separate sections.
7. Rebuild the 25-case comparison report whenever the sample roster changes:

`docs/pdf_roster_comparison_25.md`

## Do Not Do

- Do not treat every name in a transcript metadata roster as an oral advocate.
- Do not add brief-only counsel to oral-argument counts.
- Do not use the attorney general or county counsel’s institutional name as a substitute for the actual arguing attorney.
- Do not overwrite reviewed PDF overrides with regenerated transcript metadata.
- Do not assume an order lacks counsel merely because it has no conventional opinion counsel block.
