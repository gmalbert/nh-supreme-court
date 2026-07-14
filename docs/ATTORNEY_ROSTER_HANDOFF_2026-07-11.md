# Attorney Roster Handoff — 2026-07-11

## Outcome

The repository now calculates attorney and firm statistics from the Court's official oral-argument roster, rather than transcript metadata. The full rebuild currently covers all 1,071 oral-argument dockets:

- 1,069 dockets have an attorney roster.
- 2 dockets are documented as listing no attorney: `2016-0118` and `2016-0293`.
- 0 unresolved roster-source exceptions remain.
- Current statistics: 915 distinct attorneys and 564 firms.
- Current roster: 2,539 attorney entries.

The governing rebuild command is:

```bash
python3 scripts/build_pdf_attorney_roster_overrides.py --all
```

It regenerates the roster, counsel facts, attorney/firm statistics, coverage report, and exception triage in one pass.

## Source policy

- Annual NH Supreme Court oral-argument PDFs are the source of truth for oral-argument roster counsel.
- The official Court live-stream roster was used only to recover 2026 rows that were not present in the saved archive snapshot.
- Published opinions/orders provide separate brief-counsel facts; brief counsel is not counted as oral-argument counsel.
- Transcript metadata is not used as a silent fallback for attorney statistics.

## Work completed today

### Recovered complete roster coverage

- Used the official live Court 2026 roster to recover the previously missing 2026 entries.
- Confirmed the two remaining historical no-attorney cases with the user:
  - `2016-0118`
  - `2016-0293`
- The coverage and exception reports now show no unresolved source-recovery work:
  - `docs/oral_argument_roster_coverage.md`
  - `docs/oral_argument_roster_exceptions.md`

### Corrected parser artifacts

Added a durable correction overlay at `data/oral_argument_roster_corrections.json`. It is applied during every full roster build and preserves the original PDF evidence.

- Removed 37 parsed organization/party entries from attorney counts.
- Split six merged counsel fields into individual attorney records:
  - `2020-0454`: Aaron J. Curtis; Colin F. McGrath
  - `2019-0206`: Cordell A. Johnston; Stephen C. Buckley
  - `2025-0140`: David Himelfarb; John M. Allen
  - `2019-0057`: Gilles R. Bissonnette; Henry R. Klementowicz
  - `2019-0654`: Jane E. Young; Daniel E. Will
  - `2016-0569`: John Houlihan; Steven T. Whitmer
- Added two attorneys omitted by the layout parser to `2016-0558`:
  - Sean R. Cronin
  - Joseph L. DeLorey

### Normalized attorney names

Added approved high-confidence aliases to `data/attorney_name_map.json` and rebuilt statistics. This handles spacing, punctuation, missing middle initials, and clear typographical variants without overwriting raw source names.

User decision: **John M. Sullivan and John F. Sullivan are different attorneys and must remain separate.** No alias was added between them.

User-approved ambiguous mappings that were applied:

- Francis C. Fredericks → Francis C. Fredericks, Jr.
- James W. Kennedy → James W. Kennedy, III
- John J. McCormack, IV → John J. McCormack
- Richard C. Guerriero, Jr. → Richard C. Guerriero
- Silas Little → Silas Little, III

### Review tools and artifacts

- Added `scripts/generate_attorney_name_review.py` to generate the name-review queue.
- Added `scripts/build_attorney_name_review_workbook.mjs` to produce a readable Excel review workbook.
- Generated review artifacts:
  - `docs/attorney_name_review.md`
  - `outputs/attorney_name_review.xlsx`
- The workbook contains separate sheets for Instructions, Remove, Split, Map, and Organization Corrections.

### UI fix

Updated the attorney and firm profile tables so their `View` links go to Case Explorer for the docket, not the Opinions browser:

- `pages/09_Attorney_Detail.py`
- `pages/10_Firm_Detail.py`

## Verification performed

- JSON validation for correction and alias files.
- Full roster rebuild completed successfully.
- Syntax check for the roster builder.
- Verified that no organizational names listed in the approved correction file remain in `data/processed/oral_argument_roster.json`.
- Verified current coverage: 1,069 rostered dockets plus 2 confirmed no-attorney dockets.

## Remaining follow-up

1. Re-run the name-review generator after any future annual roster ingestion:

   ```bash
   python3 scripts/generate_attorney_name_review.py
   ```

2. Review any new name candidates conservatively. Do not merge people who share a last name, a first initial, or a suffix without evidence.

3. For future parser artifacts, add narrow entries to `data/oral_argument_roster_corrections.json` rather than manually editing generated JSON.

4. If future Court roster rows use a new layout, extend the parser in `scripts/build_pdf_attorney_roster_overrides.py`, add a focused test, and rebuild with `--all`.

## Important files

- `scripts/build_pdf_attorney_roster_overrides.py` — main roster parser and one-command rebuild.
- `scripts/extract_attorney_stats.py` — attorney and firm statistics from the roster.
- `data/oral_argument_roster_corrections.json` — reviewed parser corrections.
- `data/oral_argument_roster_manual_recoveries.json` — official live-source recoveries.
- `data/attorney_name_map.json` — approved canonical-name mappings.
- `data/processed/oral_argument_roster.json` — generated roster source for the application.
- `data/processed/oral_arguments_attorney_stats.json` — generated attorney and firm statistics.
