# Streamlit App Architecture

## Repository Layout

```
nh-supreme-court/
├── app.py                      # Home page / Case Explorer
├── pages/
│   ├── 01_opinions.py          # Opinions browser
│   ├── 02_justices.py          # Justice profiles & voting
│   ├── 03_analysis.py          # Analytics dashboard
│   ├── 04_topics.py            # Legal topic explorer
│   ├── 05_case_orders.py       # Non-precedential orders
│   ├── 06_search.py            # Full-text search
│   └── 07_about.py             # Methodology & info
├── scripts/
│   ├── scrape_index.py         # Scrape opinion listing pages
│   ├── download_pdfs.py        # Download PDFs
│   ├── parse_opinions.py       # PDF → structured JSON
│   ├── build_dataset.py        # Merge, validate, export CSV
│   └── update.py               # One-command refresh pipeline
├── utils/
│   ├── data_loader.py          # Cached data loading for Streamlit
│   ├── vote_parser.py          # Vote block extraction
│   ├── pdf_parser.py           # PDF text extraction
│   ├── topic_tagger.py         # Topic classification
│   ├── charts.py               # Reusable Plotly chart functions
│   └── constants.py            # Justice map, topic taxonomy, etc.
├── data/
│   ├── raw/
│   │   ├── index_2024.json
│   │   ├── index_2025.json
│   │   ├── index_2026.json
│   │   └── pdfs/
│   │       ├── 2024/
│   │       ├── 2025/
│   │       └── 2026/
│   ├── processed/
│   │   ├── opinions_2024.json
│   │   ├── opinions_2025.json
│   │   ├── opinions_2026.json
│   │   ├── all_opinions.json   # Merged master
│   │   ├── opinions.csv        # Flat export for dataframe display
│   │   ├── case_orders.csv
│   │   └── text/               # Full text per case
│   │       └── {case_number}.txt
│   ├── justices.json
│   ├── topic_taxonomy.json
│   ├── rsa_index.json
│   └── manual_corrections.json
├── data_files/
│   └── logo.png
├── .streamlit/
│   └── config.toml
├── .github/
│   └── workflows/
│       └── update_data.yml
├── docs/
│   └── data_dictionary.md
├── requirements.txt
└── README.md
```

---

## Tech Stack

### Core
| Package | Purpose |
|---------|---------|
| `streamlit` | App framework |
| `pandas` | Data manipulation |
| `plotly` | Interactive charts |
| `pdfplumber` | PDF text extraction |
| `requests` | HTTP scraping |
| `beautifulsoup4` | HTML parsing |

### Optional / Phase 2
| Package | Purpose |
|---------|---------|
| `whoosh` | Full-text search index |
| `altair` | Alternative charting (Streamlit-native) |
| `anthropic` | Claude API for AI summaries |
| `networkx` | Citation graph analysis |
| `folium` or `pydeck` | Geographic maps |

### `requirements.txt`
```
streamlit>=1.35.0
pandas>=2.0.0
plotly>=5.18.0
pdfplumber>=0.10.0
requests>=2.31.0
beautifulsoup4>=4.12.0
whoosh>=2.7.4
anthropic>=0.25.0
```

---

## Data Loading Pattern

All pages load data through `utils/data_loader.py`. Use Streamlit's `@st.cache_data` to avoid re-reading files on every interaction.

```python
# utils/data_loader.py
import streamlit as st
import pandas as pd
import json
from pathlib import Path

DATA_DIR = Path("data/processed")

@st.cache_data(ttl=3600)  # refresh hourly in production
def load_opinions() -> pd.DataFrame:
    """Load all opinions as a flat DataFrame."""
    return pd.read_csv(DATA_DIR / "opinions.csv", parse_dates=["date_argued", "date_issued"])

@st.cache_data
def load_opinions_json() -> list[dict]:
    """Load full opinion records including nested vote dicts."""
    with open(DATA_DIR / "all_opinions.json") as f:
        return json.load(f)

@st.cache_data
def load_justices() -> dict:
    with open(Path("data") / "justices.json") as f:
        return {j["key"]: j for j in json.load(f)}

@st.cache_data
def load_opinion_text(case_number: str) -> str:
    path = DATA_DIR / "text" / f"{case_number}.txt"
    return path.read_text() if path.exists() else ""
```

---

## Streamlit Config

### `.streamlit/config.toml`

```toml
[theme]
primaryColor = "#003057"          # NH state blue
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#1A1A1A"
font = "sans serif"

[server]
headless = true
enableCORS = false

[browser]
gatherUsageStats = false
```

---

## Page Template

Each page follows this structure:

```python
import streamlit as st
from utils.data_loader import load_opinions, load_justices
from utils.charts import render_vote_chart

st.set_page_config(
    page_title="NH Supreme Court — [Page Name]",
    page_icon="⚖️",
    layout="wide"
)

# --- Sidebar filters ---
with st.sidebar:
    st.header("Filters")
    year_range = st.slider("Years", 2020, 2026, (2022, 2026))
    # ... other filters

# --- Load data ---
df = load_opinions()

# --- Apply filters ---
mask = (df["citation_year"] >= year_range[0]) & (df["citation_year"] <= year_range[1])
filtered = df[mask]

# --- Main content ---
st.title("Page Title")
st.metric("Total Opinions", len(filtered))

# ... charts, tables, expanders
```

---

## Vote Chart Component (`utils/charts.py`)

```python
def render_bench_diagram(votes: dict, justices: dict) -> None:
    """Render a 5-seat NH bench diagram using Plotly."""
    import plotly.graph_objects as go

    VOTE_COLORS = {
        "majority": "#1565C0",        # blue
        "dissent": "#C62828",         # red  
        "concur_separate": "#F57F17", # amber
        "not_participating": "#9E9E9E", # gray
        "recused": "#9E9E9E",
        "disqualified": "#9E9E9E",
    }

    # 5-seat layout positions (x, y)
    SEATS = [(-2, 0), (-1, 0.2), (0, 0.3), (1, 0.2), (2, 0)]
    justice_keys = list(votes.keys())  # ordered by seniority

    fig = go.Figure()
    for i, (jkey, jvote) in enumerate(votes.items()):
        x, y = SEATS[i]
        vote_type = jvote.get("vote", "not_participating")
        color = VOTE_COLORS.get(vote_type, "#9E9E9E")
        display = jvote.get("display_name", jkey)
        
        fig.add_trace(go.Scatter(
            x=[x], y=[y],
            mode="markers+text",
            marker=dict(size=60, color=color),
            text=[display.split(",")[0]],
            textposition="bottom center",
            hovertext=f"{display}: {vote_type}",
            hoverinfo="text",
            showlegend=False,
        ))

    fig.update_layout(
        height=250,
        xaxis=dict(visible=False, range=[-3, 3]),
        yaxis=dict(visible=False, range=[-0.5, 1]),
        margin=dict(l=0, r=0, t=10, b=30),
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)
```

---

## GitHub Actions — Auto Update

### `.github/workflows/update_data.yml`

```yaml
name: Update NH Supreme Court Data

on:
  schedule:
    - cron: '0 10 * * 1'  # Every Monday at 10am UTC
  workflow_dispatch:       # Manual trigger

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          
      - name: Install dependencies
        run: pip install -r requirements.txt
        
      - name: Scrape new opinions
        run: python scripts/update.py
        
      - name: Commit updated data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          git diff --staged --quiet || git commit -m "Auto-update: NH SC opinions $(date +%Y-%m-%d)"
          git push
```

---

## Deployment

### Streamlit Community Cloud (recommended for MVP)
- Connect to GitHub repo
- Set `app.py` as main file
- Free tier handles this workload easily
- Data files committed to repo → no external DB needed

### Local Development
```bash
git clone https://github.com/[you]/nh-supreme-court
cd nh-supreme-court
pip install -r requirements.txt
python scripts/update.py  # build initial dataset
streamlit run app.py
```
