# Data Collection Strategy

## Overview

Since the NH Supreme Court publishes no structured API, the pipeline has three stages:
1. **Scrape** the opinions index page → get PDF links and basic metadata
2. **Download** PDFs
3. **Parse** PDFs → extract structured fields

All scripts live in `scripts/`. Outputs land in `data/raw/` (PDFs) and `data/processed/` (JSON/CSV).

---

## Stage 1: Index Scraping

### Target URLs

```
https://www.courts.nh.gov/our-courts/supreme-court/orders-and-opinions/opinions/{year}
https://www.courts.nh.gov/our-courts/supreme-court/orders-and-opinions/case-orders/{year}
```

Scrape years 2020–present initially. Older years may have different HTML structure.

### Script: `scripts/scrape_index.py`

**Approach:**
- Use `requests` + `BeautifulSoup` to parse the opinions listing page
- The page likely lists each opinion as a row with: case name, case number, date filed, and a PDF link
- Extract all `<a>` tags pointing to `.pdf` files
- Also extract any inline text (case name, docket number, date) adjacent to each link

**Expected fields from index page:**
| Field | Source |
|-------|--------|
| `case_name` | Link text or adjacent cell |
| `case_number` | Adjacent text, pattern `20XX-XXXX` |
| `date_issued` | Adjacent date cell |
| `pdf_url` | `href` attribute of link |
| `opinion_type` | `"opinion"` or `"case_order"` (from which index page) |
| `year` | From URL |

**Output:** `data/raw/index_{year}.json`

### Handling 403 / Access Issues

The court site returned a 403 when fetched without a browser user-agent. Fix:

```python
headers = {
    "User-Agent": "Mozilla/5.0 (compatible; NH-SC-Analyzer/1.0; research use)"
}
response = requests.get(url, headers=headers)
```

Add a `time.sleep(1)` between requests to be courteous.

---

## Stage 2: PDF Download

### Script: `scripts/download_pdfs.py`

- Reads `data/raw/index_{year}.json`
- Downloads each PDF to `data/raw/pdfs/{year}/{case_number}.pdf`
- Skips already-downloaded files (idempotent)
- Logs failures to `data/raw/download_errors.json`

**Note:** PDFs are the court's canonical source. Store them permanently — the court sometimes removes or replaces PDFs after corrections.

---

## Stage 3: PDF Parsing

### Script: `scripts/parse_opinions.py`

**Library:** `pdfplumber` (preferred over PyPDF2 for layout-aware text extraction)

```
pip install pdfplumber
```

### Text Extraction Approach

NH Supreme Court opinions follow a consistent template. Extract using a combination of regex and positional parsing:

#### 3a. Header Block (first page)

```
THE SUPREME COURT OF NEW HAMPSHIRE
___________________________
[Court/District name]
Case No. [XXXX-XXXX]
Citation: [Case Name], 20XX N.H. [seq]

[PARTY A]
v.
[PARTY B]

Argued: [Month Day, Year]
Opinion Issued: [Month Day, Year]
```

Regex patterns:
```python
CASE_NO_RE = re.compile(r"Case No\.\s+(\d{4}-\d{4})")
CITATION_RE = re.compile(r"Citation:\s+(.+),\s+(\d{4})\s+N\.H\.\s+(\d+)")
ARGUED_RE = re.compile(r"Argued:\s+(.+)")
ISSUED_RE = re.compile(r"Opinion Issued:\s+(.+)")
DISTRICT_RE = re.compile(r"THE SUPREME COURT OF NEW HAMPSHIRE\s+_+\s+(.+?)\s+Case No\.", re.DOTALL)
```

#### 3b. Parties

Pattern: Text between the citation block and "Argued:" line.  
The `v.` separator distinguishes appellant from appellee.  
Watch for: multi-party cases, "IN THE MATTER OF", "PETITION OF" formats (no `v.`).

#### 3c. Counsel Block

Text between the "Opinion Issued:" line and the "PER CURIAM." or justice byline. Contains attorney names and firms for each party. Parse to extract:
- Petitioner/appellant counsel
- Respondent/appellee counsel
- Amicus counsel (if any)
- AG appearances (pattern: "John M. Formella, attorney general")

#### 3d. Opinion Author

Look for the author byline immediately after the counsel block:
- `DONOVAN, J.` — authored by Donovan
- `PER CURIAM.` — unanimous per curiam (no single author)
- `MACDONALD, C.J.` — authored by Chief Justice

Regex:
```python
AUTHOR_RE = re.compile(
    r"^(PER CURIAM|([A-Z\-]+),\s+(C\.J\.|J\.))[\.\s]",
    re.MULTILINE
)
```

#### 3e. Concurrence / Vote Line

The final paragraph(s) contain the vote breakdown. Look for the signature block at the end of the opinion:

**Pattern 1 — Concurrence line:**
```
DONOVAN, COUNTWAY, GOULD, and WILL, JJ., concurred;
MACDONALD, C.J., sat for oral argument but subsequently disqualified himself and did not participate in further review of the case.
```

**Pattern 2 — Simple concurrence:**
```
MACDONALD, C.J., and COUNTWAY and GOULD, JJ., concurred.
```

**Extraction logic:**
1. Find the last 10 lines of the opinion
2. Match justice name patterns: `[A-Z\-]+,\s+(C\.J\.|J\.)`
3. Classify each as: `majority`, `concur`, `dissent`, `recused`, `disqualified`, `not_participating`
4. The author is implicitly in the majority; concurring justices listed at end join the majority unless labeled "dissenting" or "concurring separately"

#### 3f. Topic / Issue Area Tagging

NH opinions don't self-tag by issue area (unlike Oyez). Use keyword extraction:

**Approach A (rule-based):** Match legal keywords against a lookup table → assign tags.

```python
TOPIC_KEYWORDS = {
    "criminal": ["criminal", "indictment", "defendant", "RSA 625", "RSA 626", "RSA 630", "RSA 631", "RSA 632", "RSA 633"],
    "competency": ["competency", "competent to stand trial", "RSA 135:17"],
    "insurance": ["insurance", "insurer", "insured", "liquidation", "RSA 402"],
    "medicaid": ["medicaid", "MCO", "managed care", "RSA 126-A", "DHHS"],
    "administrative_law": ["administrative", "AAU", "certiorari", "jurisdiction", "RSA 541"],
    "family_law": ["divorce", "parenting", "custody", "RSA 458"],
    "civil_procedure": ["summary judgment", "motion to dismiss", "RSA 508"],
    "statutory_interpretation": ["plain meaning", "statutory interpretation", "construe", "legislative intent"],
    "constitutional": ["constitutional", "First Amendment", "due process", "equal protection"],
    "property": ["property", "easement", "zoning", "RSA 674", "RSA 676"],
    "employment": ["employment", "workers compensation", "RSA 281"],
    "contract": ["contract", "breach", "damages"],
    "tort": ["negligence", "liability", "personal injury"],
    "evidence": ["hearsay", "Rule 403", "admissibility"],
}
```

**Approach B (LLM-assisted, optional):** Feed the opinion summary to Claude API → get structured topic tags. Good for ambiguous cases.

#### 3g. RSA Citations

Extract all RSA references — these are the NH statutory citations and are analytically valuable:

```python
RSA_RE = re.compile(r"RSA\s+[\d\-A-Z:]+(?:,?\s+[IVX]+)?")
```

Store as a list. These enable filtering by statute, finding all cases touching RSA 135, etc.

#### 3h. Case Summary

Extract the introductory paragraph(s) — typically ¶1–¶2 — as a plain-language preview. These usually state what the case is about and the outcome ("We affirm," "We reverse and remand," etc.).

**Outcome detection:**
```python
OUTCOME_RE = re.compile(
    r"\b(affirm|reverse|remand|vacate|dismiss|affirmed|reversed|remanded|vacated|dismissed)\b",
    re.IGNORECASE
)
```

Store the primary outcome verb.

---

## Output Schema (per opinion)

See `02_data_schema.md` for the full field list.

**Output file:** `data/processed/opinions_{year}.json` — list of opinion dicts.  
**Master file:** `data/processed/all_opinions.json` — merged across all years.  
**CSV export:** `data/processed/opinions.csv` — flat version for Streamlit `st.dataframe`.

---

## Incremental Updates

Run the pipeline on a schedule (e.g., weekly GitHub Action):

1. Scrape index → find new PDFs not yet in `data/raw/`
2. Download new PDFs only
3. Parse new PDFs → append to `data/processed/`
4. Commit updated data files

The GitHub Actions workflow (`.github/workflows/update_data.yml`) handles this automatically.

---

## Case Orders Pipeline

Same pipeline, simpler parsing. Case orders are shorter and often don't have full opinion text. Extract:
- Case number
- Date
- Case name
- Order type (e.g., "Motion Denied", "Remanded", "Dismissed")
- Any justice signatures

Store in `data/processed/case_orders_{year}.json`.

---

## Manual Override / Correction

Maintain a `data/manual_corrections.json` file where known parsing errors can be corrected by hand. The pipeline merges manual corrections over automated output during the build step.
