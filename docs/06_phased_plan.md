# Phased Build Plan

---

## Phase 0 — Groundwork (Days 1–3)

Get the data pipeline working before writing a single line of Streamlit.

### Goals
- [ ] Confirm you can successfully fetch the NH court's opinion listing page (test user-agent strings if needed)
- [ ] Download 10–20 PDFs from 2025–2026 manually as a test corpus
- [ ] Get `pdfplumber` extracting clean text from NH opinion PDFs
- [ ] Validate that the header block (case number, citation, parties, dates) parses correctly for all test PDFs
- [ ] Validate that the vote block parses correctly for all test PDFs
- [ ] Build `data/justices.json` with current roster (pull from court website)

### Deliverables
- `scripts/parse_opinions.py` — working on test corpus
- `data/justices.json` — complete
- `data/topic_taxonomy.json` — initial version
- `data/rsa_index.json` — RSA chapter → name mapping (chapters 1–700)

### Watch For
- PDFs that have unusual formatting (e.g., older opinions with different headers)
- PDFs where text extraction fails (scanned images) — NH court opinions should all be text-based, not scans
- The "NOTICE:" preamble block — strip this before parsing begins
- Counsel blocks with unusual line wrapping

---

## Phase 1 — MVP Data Pipeline (Days 4–7)

Full automated pipeline for 2024–2026 opinions.

### Goals
- [ ] `scripts/scrape_index.py` — scrapes listing page, produces `index_{year}.json`
- [ ] `scripts/download_pdfs.py` — downloads all PDFs idempotently
- [ ] `scripts/parse_opinions.py` — parses all PDFs, produces `opinions_{year}.json`
- [ ] `scripts/build_dataset.py` — merges years, produces `all_opinions.json` + `opinions.csv`
- [ ] `scripts/update.py` — single command that runs all four in sequence
- [ ] Parse 2024, 2025, 2026 opinions fully
- [ ] Manual review of 20 random records to check parsing accuracy
- [ ] Fix any systematic errors found

### Acceptance Criteria
- ≥95% of opinions have correct: case_number, citation, date_issued, author, outcome
- ≥90% of opinions have correct vote breakdown
- ≥85% of opinions have at least one topic tag
- Zero crash-inducing errors on any PDF in corpus

---

## Phase 2 — Core App (Days 8–14)

Build the Streamlit app with the three most useful pages first.

### Priority Order

**1. Home / Case Explorer (`app.py`)**
- Year + case selector in sidebar
- Case detail card
- Bench diagram vote visualization
- Basic metadata display

**2. Opinions Browser (`pages/01_opinions.py`)**
- Full table with key columns
- Sidebar filters: year, outcome, topic, justice
- Row click → detail panel
- Download filtered results as CSV

**3. Justices (`pages/02_justices.py`)**
- Justice selector → profile card
- Voting record table
- Agreement matrix heatmap (5x5)
- Authorship bar chart

### Acceptance Criteria
- App runs locally without errors
- All three pages load in < 3 seconds on the full 2024–2026 dataset
- Filters work correctly (test edge cases: no results, single result)
- Bench diagram renders correctly for all vote patterns in the corpus

---

## Phase 3 — Analysis & Topics (Days 15–21)

Add the analytical depth.

### Goals
- [ ] `pages/03_analysis.py` — Term Statistics, Statutory Spotlight, Win Rates, Close Decisions tabs
- [ ] `pages/04_topics.py` — Topic browser, RSA Tracker
- [ ] Refine topic tagging (review auto-tagged results, adjust keyword lists)
- [ ] Add RSA → statute name lookup throughout the app

### New Data Work
- [ ] Extend parse to extract counsel names reliably
- [ ] Compute `days_to_decision` for all opinions
- [ ] Compute `outcome_for` (who won) — this requires some heuristic logic

---

## Phase 4 — Case Orders & Search (Days 22–28)

### Goals
- [ ] `pages/05_case_orders.py` — orders table and activity timeline
- [ ] `scripts/parse_case_orders.py` — simpler parser for non-precedential orders
- [ ] `pages/06_search.py` — full-text search with `whoosh`
  - Build index from `data/processed/text/*.txt`
  - Search returns ranked results with highlighted snippets
  - Filter by year/topic/outcome after search

---

## Phase 5 — Historical Depth & Polish (Days 29–45)

Extend the dataset and improve UX.

### Goals
- [ ] Back-fill 2020, 2021, 2022, 2023 opinions (may have different HTML structure on court site)
- [ ] `pages/07_about.py` — methodology, known parsing issues, justice roster
- [ ] Improve topic classification — review all opinions with no topic tag
- [ ] Counsel analytics tab in Analysis page
- [ ] Geographic view: NH county map, reversal rate by lower court
- [ ] Set up GitHub Actions for weekly auto-update

### UX Polish
- [ ] Add `st.spinner` and loading states throughout
- [ ] Add "Last updated:" timestamp to sidebar
- [ ] Mobile-friendly layout check (Streamlit auto-handles most of this)
- [ ] NH state branding (blue/gold color scheme, NH seal)
- [ ] Error states for empty filter results

---

## Phase 6 — AI Features (Optional / Post-Launch)

Use Claude API to enhance the app.

### AI Summary Generation
For opinions where `summary_paragraph` is dense or technical, generate a plain-language summary:

```python
import anthropic

def generate_plain_summary(opinion_text: str, case_name: str) -> str:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": f"""You are a legal educator writing for a general audience.
Summarize this NH Supreme Court opinion in 2-3 plain-language sentences.
Focus on: what happened, what the legal question was, and how the court ruled.
Avoid jargon.

Case: {case_name}
Opinion text (first 2000 chars):
{opinion_text[:2000]}"""
        }]
    )
    return response.content[0].text
```

Run this as a batch script, store results in `data/processed/ai_summaries.json`, display in the app.

### Topic Classification Enhancement
Feed opinion text to Claude for more accurate topic tagging, especially for edge cases where keyword matching fails.

### "Ask About This Case" Chat
Add an `st.chat_input` to the case detail page → user can ask questions about the opinion, answered by Claude with the full opinion text as context.

---

## Known Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Court website structure changes, breaking scraper | Medium | Store all raw PDFs; only re-scrape index pages; add scraper health check |
| PDF formatting varies across years | High | Test against full historical corpus early; add manual_corrections.json escape hatch |
| Vote block parsing fails on unusual opinions | Medium | Flag `parse_confidence < 0.7` in UI; manual correction workflow |
| Court blocks automated scraping | Low | Use respectful scraping (delays, user-agent, infrequent schedule); reach out to court if needed |
| Justice roster changes (appointment, retirement) | Medium | Update `justices.json` manually; subscribe to court news |
| RSA chapter re-numbering (rare legislative event) | Very Low | RSA index is a lookup table; update manually if needed |

---

## Success Metrics

**Phase 2 Launch (internal/beta):**
- All 2024–2026 opinions parsed and browsable
- Bench diagram correct for all opinions
- Justice agreement matrix computable

**Phase 5 Launch (public):**
- 2020–2026 coverage (~300–400 opinions)
- Full-text search working
- Weekly auto-update running
- Page load times < 3 seconds
- Zero crash bugs in 1 week of use

**Phase 6 (nice-to-have):**
- AI summaries for all opinions
- "Ask about this case" working
- 2010+ historical coverage
