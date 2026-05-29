# Data Schema

## Opinion Record

Each parsed opinion produces one JSON object with the following fields.

### Core Identity

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `case_number` | str | `"2025-0028"` | NH docket number; unique identifier |
| `citation` | str | `"2026 N.H. 18"` | Official NH citation |
| `citation_year` | int | `2026` | Year portion of citation |
| `citation_seq` | int | `18` | Sequential number within year |
| `case_name` | str | `"State v. Freese"` | Short case name |
| `case_name_full` | str | `"THE STATE OF NEW HAMPSHIRE v. DONALD FREESE"` | Full as printed in opinion |
| `pdf_url` | str | `"https://..."` | Source PDF URL |
| `pdf_local_path` | str | `"data/raw/pdfs/2026/2025-0028.pdf"` | Local file path |

### Dates

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `date_argued` | str | `"2026-03-10"` | ISO format; null if not argued (e.g., submitted on briefs) |
| `date_issued` | str | `"2026-04-24"` | ISO format |
| `days_to_decision` | int | `45` | Computed: issued - argued |
| `term_year` | int | `2026` | Court term year |

### Court & Procedural

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `lower_court` | str | `"Hillsborough-northern judicial district"` | As printed in header |
| `lower_court_type` | str | `"superior_court"` | Normalized: `superior_court`, `district_court`, `family_court`, `probate_court`, `administrative`, `dhhs`, `other` |
| `case_type` | str | `"criminal"` | Normalized case type based on party structure and content |
| `appeal_type` | str | `"standard"` | `standard`, `interlocutory`, `certiorari`, `original_jurisdiction` |
| `outcome` | str | `"reversed"` | Primary outcome verb: `affirmed`, `reversed`, `remanded`, `reversed_and_remanded`, `vacated`, `dismissed`, `affirmed_and_remanded` |
| `outcome_for` | str | `"defendant"` | Who won: `appellant`, `appellee`, `defendant`, `state`, `petitioner`, `respondent`, `mixed` |

### Parties

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `party_appellant` | str | `"Donald Freese"` | Name of appealing party |
| `party_appellee` | str | `"State of New Hampshire"` | Responding party |
| `party_type_appellant` | str | `"individual"` | `individual`, `state`, `business`, `government`, `municipality`, `insurer`, `other` |
| `party_type_appellee` | str | `"state"` | Same categories |
| `ag_appeared` | bool | `true` | Whether AG's office appeared (signals state interest) |
| `ag_side` | str | `"appellee"` | Which side the AG argued for |

### Justices & Voting

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `author` | str | `"per_curiam"` | Justice last name (lowercase) or `per_curiam` |
| `author_display` | str | `"Per Curiam"` | Display-formatted version |
| `votes` | dict | See below | Per-justice vote record |
| `vote_majority` | int | `5` | Count in majority |
| `vote_dissent` | int | `0` | Count dissenting |
| `vote_concur_separate` | int | `0` | Separate concurrences |
| `vote_not_participating` | int | `1` | Recused, disqualified, or absent |
| `vote_string` | str | `"4-0"` | Shorthand (excludes non-participants) |
| `is_unanimous` | bool | `true` | True if no dissents |
| `has_dissent` | bool | `false` | |
| `has_separate_concurrence` | bool | `false` | |

#### `votes` sub-object

```json
{
  "macdonald": {
    "display_name": "MacDonald, C.J.",
    "role": "chief_justice",
    "vote": "not_participating",
    "note": "sat for oral argument but subsequently disqualified himself"
  },
  "donovan": {
    "display_name": "Donovan, J.",
    "role": "associate_justice",
    "vote": "majority",
    "note": null
  },
  "countway": {
    "display_name": "Countway, J.",
    "role": "associate_justice",
    "vote": "majority",
    "note": null
  },
  "gould": {
    "display_name": "Gould, J.",
    "role": "associate_justice",
    "vote": "majority",
    "note": null
  },
  "will": {
    "display_name": "Will, J.",
    "role": "associate_justice",
    "vote": "majority",
    "note": null
  }
}
```

**Vote values:** `majority`, `dissent`, `concur_separate`, `not_participating`, `recused`, `disqualified`

### Legal Content

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `topics` | list[str] | `["criminal", "competency", "statutory_interpretation"]` | Multi-select tags |
| `rsa_citations` | list[str] | `["RSA 135:17-a", "RSA 135-C:34"]` | All RSA references found in text |
| `rsa_primary` | str | `"RSA 135:17-a"` | Most-cited RSA (heuristic) |
| `constitutional_issues` | list[str] | `[]` | Constitutional provisions at issue |
| `involves_statutory_interpretation` | bool | `true` | Detected from text |
| `standard_of_review` | list[str] | `["de_novo"]` | `de_novo`, `abuse_of_discretion`, `clear_error`, `substantial_evidence`, `plain_error` |

### Text Content

| Field | Type | Notes |
|-------|------|-------|
| `summary_paragraph` | str | First substantive paragraph (¶1 or ¶2), plain text |
| `holding` | str | Extracted or inferred holding statement |
| `full_text` | str | Complete extracted text — store separately in `data/processed/text/{case_number}.txt` |
| `word_count` | int | Length of full_text in words |

### Counsel

| Field | Type | Notes |
|-------|------|-------|
| `counsel_appellant` | list[str] | Attorney names for appellant |
| `counsel_appellee` | list[str] | Attorney names for appellee |
| `counsel_amicus` | list[str] | Amicus counsel, if any |
| `firms_appellant` | list[str] | Law firms for appellant |
| `firms_appellee` | list[str] | Law firms for appellee |

### Meta

| Field | Type | Notes |
|-------|------|-------|
| `parse_version` | str | Parser version that generated this record |
| `parse_timestamp` | str | ISO datetime of when parsing occurred |
| `parse_confidence` | float | 0.0–1.0; lower = more fields were fallback/heuristic |
| `manual_override` | bool | True if `manual_corrections.json` modified this record |

---

## Case Order Record

Simpler schema for non-precedential orders:

| Field | Type | Notes |
|-------|------|-------|
| `case_number` | str | Docket number |
| `case_name` | str | |
| `date_issued` | str | ISO format |
| `order_type` | str | `motion_denied`, `motion_granted`, `dismissed`, `remanded`, `stayed`, `other` |
| `justices_signing` | list[str] | Justice last names who signed |
| `pdf_url` | str | |
| `summary` | str | First sentence or two of order text |
| `term_year` | int | |

---

## Justice Reference Table

Maintained in `data/justices.json`. See `04_justice_reference.md` for full details.

| Field | Type |
|-------|------|
| `key` | str — lowercase last name, used as dict key |
| `last_name` | str |
| `first_name` | str |
| `display_name` | str — e.g., `"Donovan, J."` |
| `role` | str — `chief_justice` or `associate_justice` |
| `appointed_by` | str — appointing governor |
| `date_appointed` | str |
| `date_retired` | str or null |
| `is_active` | bool |
| `political_affiliation` | str — appointing governor's party |

---

## Normalized Lookup Tables

### `data/topic_taxonomy.json`
Maps topic tags to human-readable labels and descriptions.

### `data/rsa_index.json`
Maps RSA chapter numbers to statute names (e.g., `"135"` → `"Mental Health"`).

### `data/lower_courts.json`
Maps raw lower court strings to normalized types and geographic regions.
