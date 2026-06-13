# Granite State Appeals — GitHub Copilot Instructions

## Project Overview

**App name:** Granite State Appeals
**Purpose:** Public-facing Streamlit app for exploring the New Hampshire Supreme Court — decisions, orders, justices, case topics, and voting patterns.
**Entry point:** `streamlit run cases.py`
**Data source:** NH Supreme Court public opinions and orders (scraped/downloaded)

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit ≥ 1.36 (multi-page via `st.navigation`) |
| Data | pandas, local CSV/JSON data files |
| Viz | Plotly (`utils/charts.py`) |
| Config | None — all data is public |
| Python | 3.9+ |

---

## File Conventions

### Key files
- `cases.py` — entry point; sets `st.set_page_config` ONCE; wires navigation.
- `utils/data_loader.py` — `load_opinions()`, `load_opinions_json()`, `load_opinion_text()`, `data_last_updated()`.
- `utils/constants.py` — `APP_NAME`, `APP_TAGLINE`, `OUTCOME_COLORS`, `OUTCOME_LABELS`, `VOTE_COLORS`.
- `utils/charts.py` — shared Plotly chart builders including `bench_diagram()`.
- `utils/vote_parser.py` — parsing vote/disposition strings from raw opinions.
- `update_pipeline.ps1` — PowerShell script to fetch and refresh opinion data.
- `download_log.txt` — tracks download history for incremental updates.

### Pages
- `pages/01_Opinions.py` — case/opinion explorer with search and filters
- `pages/02_Justices.py` — justice profiles, tenure, voting stats
- `pages/03_Analysis.py` — voting patterns, majority/dissent analysis
- `pages/04_Topics.py` — cases by legal topic area
- `pages/05_Case_Orders.py` — court orders (shorter procedural rulings)
- `pages/06_About.py` — about page and data sources
- `pages/07_Trial_Courts.py` — origin trial courts breakdown

### Data files
- `data_files/logo.png` — app logo
- `data_files/` — cached CSV/JSON opinion and order data
- `data/` — raw downloaded data from NH courts website
- `orders/` — downloaded PDF/text court orders
- `docs/` — documentation and update guides

---

## Domain Knowledge

### NH Supreme Court structure
- 5 justices: Chief Justice + 4 Associate Justices
- Cases originate from NH Superior, District, or Family Courts
- Key outcome types: Affirmed, Reversed, Remanded, Vacated
- Opinions may be: published (citable precedent) or unpublished

### Opinion data fields
- `docket_number` — primary identifier (e.g. `"2024-0123"`)
- `date_decided` — decision date
- `author` — writing justice
- `disposition` — Affirmed/Reversed/Remanded/etc.
- `topic` — legal topic area
- `votes` — vote breakdown if available

---

## Coding Conventions

### Streamlit patterns
```python
@st.cache_data(ttl=3600)
def load_opinions() -> pd.DataFrame: ...
```
- `st.set_page_config()` called ONCE in `cases.py` only
- Sub-pages must NOT call `st.set_page_config`
- Use `width='stretch'` for dataframes (not deprecated `use_container_width`)
- All data loaded via `utils/data_loader.py` — no direct file I/O in page files

### Data pipeline
- Run `update_pipeline.ps1` to refresh opinions from the NH courts website
- New downloads logged to `download_log.txt` for incremental tracking
- Always sort opinions by date descending before display

### Error handling
- Check `if df.empty` before rendering tables
- Use `st.info()` for missing data, not exceptions
- Guard all date formatting against None/NaT values
