# Granite State Appeals (NH Supreme Court) — Next 5 Features to Implement

> **Based on:** Codebase gap analysis as of July 2025

---

## Feature 1: Automated Nightly Scraping (GitHub Actions)

**Why:** The scraper must currently be run manually to update data. Adding a GitHub Actions workflow that runs `scripts/scrape_3jx.py` nightly and commits updated CSV files would make the app self-updating without any manual intervention.

**How:**
1. Create `.github/workflows/nightly_scrape.yml` with a cron trigger at `04:00 UTC` daily
2. Steps: checkout → setup Python → install requirements → run `scripts/scrape_3jx.py` → run `scripts/parse_opinions.py` → git add/commit/push if new data exists
3. Use `download_log.txt` to detect whether new opinions were actually scraped (skip commit if nothing new)
4. Add "Data last updated" display in the Streamlit sidebar sourced from the log file

**Complexity:** Low

---

## Feature 2: Full-Text Opinion Search

**Why:** The current app allows filtering by case title, topic, and justice — but not by text within the opinion body. Full-text search would allow researchers to find all opinions mentioning "Fourth Amendment" or "harmless error" — the most powerful research use case.

**How:**
1. In `utils/data_loader.py`, load opinion text (if scraped) alongside metadata
2. Build a TF-IDF index using `sklearn.feature_extraction.text.TfidfVectorizer` over opinion text bodies
3. Add a search bar (`st.text_input`) on `pages/01_Opinions.py` that queries the TF-IDF index
4. Return and display ranked results: case name, date, snippet with search term highlighted
5. Cache the TF-IDF index with `@st.cache_resource` to avoid rebuilding on each navigation

**Complexity:** Medium

---

## Feature 3: Citation Network Graph

**Why:** NH Supreme Court opinions cite prior cases in their text. A citation network (nodes = cases, directed edges = citations) would reveal which precedents are most influential and how legal doctrines evolve across decades — a unique research visualization.

**How:**
1. In `scripts/parse_opinions.py`, add regex citation extraction: match NH case citation patterns (e.g., "123 N.H. 456" or "In re: ___")
2. Build a citation edge list: `citing_case_id → cited_case_id`
3. Add `pages/06_Citation_Network.py` using NetworkX to compute the graph + Plotly for interactive rendering
4. Show: top 20 most-cited cases, shortest path between two user-selected cases, clustering by legal topic

**Complexity:** Medium

---

## Feature 4: Justice Agreement Heatmap (Interactive)

**Why:** The Justice voting patterns page already shows some agreement data but a full pairwise heatmap with drill-down would be far more informative. Which two justices agree most often? Which pairs form consistent minority blocs?

**How:**
1. For each pair of justices, compute: `agreement_rate = matches_in_same_vote_position / total_shared_cases`
2. Render as an interactive Plotly heatmap (color scale: 0–100% agreement)
3. Add click/hover interactivity: clicking a cell shows the list of cases where this pair disagreed
4. Add a topic filter dropdown: "Show agreement rate on criminal cases only"

**Complexity:** Low

---

## Feature 5: Mobile-Optimized Responsive Layout

**Why:** Streamlit's default layout is not mobile-friendly. Researchers and attorneys accessing NH court data on mobile devices would benefit significantly from a responsive layout — collapsible sidebar, full-width tables, and larger tap targets.

**How:**
1. Inject custom CSS via `st.markdown(unsafe_allow_html=True)` in `cases.py` to:
   - Hide the sidebar on mobile (< 768px) by default: `[data-testid="stSidebar"] { display: none; }`
   - Add a hamburger-style toggle button to show/hide the sidebar on mobile
   - Make tables scroll horizontally: `overflow-x: auto`
2. Replace wide multi-column layouts with `st.expander` blocks on narrow viewports
3. Test in Chrome DevTools mobile emulation before deploying

**Complexity:** Low
