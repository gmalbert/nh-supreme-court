# Granite State Appeals — Architecture

## Overview
Public-facing Streamlit app for exploring NH Supreme Court decisions, orders, justices, and voting patterns. All data is public; no authentication required.

## Data Flow
```
NH Supreme Court website (public opinions + orders)
        ↓
update_pipeline.ps1 (PowerShell data pipeline)
        ↓
data/raw/ downloads → data_files/ (CSV/JSON processed)
download_log.txt (incremental tracking)
        ↓
utils/data_loader.py → load_opinions(), load_opinions_json(), data_last_updated()
        ↓
cases.py (Streamlit entry) → st.navigation → pages/
```

## Data Model
### Opinion fields
| Field | Description |
|-------|-------------|
| `docket_number` | Primary identifier (e.g. `"2024-0123"`) |
| `date_decided` | Decision date |
| `author` | Writing justice |
| `disposition` | Affirmed / Reversed / Remanded / Vacated |
| `topic` | Legal topic area |
| `votes` | Vote breakdown (if available) |

### Court Structure
- 5 justices: Chief Justice + 4 Associate Justices
- Cases originate from Superior, District, or Family Courts
- Published opinions = citable precedent; unpublished = not citable

## Key Components
- `cases.py` — entry, `st.set_page_config`, navigation wiring
- `utils/data_loader.py` — `load_opinions()`, `load_opinions_json()`, `load_opinion_text()`, `data_last_updated()`
- `utils/constants.py` — `APP_NAME` ("Granite State Appeals"), `APP_TAGLINE`, `OUTCOME_COLORS`, `OUTCOME_LABELS`, `VOTE_COLORS`
- `utils/charts.py` — Plotly chart builders including `bench_diagram()`
- `utils/vote_parser.py` — parsing vote/disposition strings from raw opinion text
- `update_pipeline.ps1` — PowerShell script to refresh opinion data from NH courts site
- `download_log.txt` — tracks downloaded opinions for incremental updates

## Pages
| Page | Purpose |
|------|---------|
| `01_Opinions.py` | Case/opinion explorer with search and filters |
| `02_Justices.py` | Justice profiles, tenure, voting stats |
| `03_Analysis.py` | Voting patterns, majority/dissent analysis |
| `04_Topics.py` | Cases by legal topic area |
| `05_Case_Orders.py` | Court orders (shorter procedural rulings) |
| `06_About.py` | About page and data sources |
| `07_Trial_Courts.py` | Origin trial courts breakdown |

## Storage
- `data_files/` — processed CSV/JSON opinion data
- `data/` — raw downloaded data from NH courts
- `orders/` — downloaded PDF/text court orders
- `docs/` — documentation and update guides
- `logs/` — pipeline run logs
- `download_log.txt` — incremental download tracking

## No ML
This app is entirely data-driven — no machine learning models. Analysis is descriptive (voting rates, author statistics, topic frequency, justice tenure).
