> **AI Onboarding Guide** — See also the project README for background context.

# Granite State Appeals (NH Supreme Court) — Site Summary

## What This App Does

Streamlit analytics app for New Hampshire Supreme Court opinions. Scrapes the NH 3JX judicial portal (Selenium), extracts opinion metadata (justices, vote outcomes, topics, authors), and displays trends via interactive charts and tables. Five pages: Opinions search, Justice voting patterns, Opinion topics, Author analysis, and Trial Court statistics.

## Quick Start

```bash
# 1. Activate virtual environment
.\.venv\Scripts\Activate.ps1        # Windows
source .venv/bin/activate           # macOS/Linux

# 2. (One-time or periodic) Run scrapers to populate data
python scripts/scrape_3jx.py        # Scrapes NH 3JX portal (requires Chrome/Selenium)
python scripts/scrape_index.py      # Scrapes opinion index
python scripts/parse_opinions.py    # Parses HTML → structured CSV

# 3. Run the app
streamlit run cases.py
```

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit (multi-page, `st.navigation`) |
| Scraping | Selenium (Chrome) + BeautifulSoup4 |
| Data storage | CSV (processed opinions), JSON (justices metadata) |
| Visualization | Plotly |
| Caching | `@st.cache_data` in `utils/data_loader.py` |

## Key Files

| File | Purpose |
|---|---|
| `cases.py` | Streamlit entry point |
| `utils/data_loader.py` | All `@st.cache_data` data loading functions |
| `pages/01_Opinions.py` | Searchable opinion list with metadata filters |
| `pages/02_Justices.py` | Justice voting patterns and agreement analysis |
| `pages/03_Topics.py` | Topic frequency and trend analysis |
| `pages/04_Authors.py` | Authorship statistics per justice |
| `pages/05_Trial_Court.py` | Trial court reversal and appeal statistics |
| `scripts/scrape_3jx.py` | Selenium scraper for NH 3JX judicial portal |
| `scripts/scrape_index.py` | Opinion index scraper |
| `scripts/parse_opinions.py` | HTML parser → structured CSV |
| `data/processed/` | Processed CSV files (opinions, justices, vote data) |

## Data Flow

1. **Scrape**: `scripts/scrape_3jx.py` → Selenium navigates NH 3JX portal → raw HTML
2. **Parse**: `scripts/parse_opinions.py` → extracts opinion metadata (date, justices, vote breakdown, topic, trial court)
3. **Storage**: `data/processed/*.csv` + `data/justices.json`
4. **UI**: `utils/data_loader.py` reads CSVs with `@st.cache_data` → 5 pages render charts/tables

## Environment Variables

No API keys required. The scraper accesses the NH 3JX public website directly. Chrome/ChromeDriver must be installed for Selenium.

## Critical Conventions

- Data updates require running scrape scripts manually — no automated scheduling is set up
- All data loading goes through `utils/data_loader.py` with `@st.cache_data` — never read files directly in page code
- `st.set_page_config()` is called only in `cases.py` — never in page files

## Common Gotchas

- The Selenium scraper requires Chrome and ChromeDriver — version must match installed Chrome
- If NH 3JX portal changes its HTML structure, `scripts/parse_opinions.py` will need updating
- Scraping rate: add appropriate delays to `scrape_3jx.py` to avoid being blocked
- `download_log.txt` tracks which opinions have already been downloaded — check it before re-running the scraper
