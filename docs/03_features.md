# App Features — Page by Page

All pages are Streamlit `.py` files in `pages/`. The main `app.py` is the home/landing page.

---

## Home (`app.py`) — Case Explorer

Quick single-case lookup. The entry point for most users.

### Layout
- **Sidebar:** Year selector → Case selector (populates from filtered data)
- **Main area:** Case detail card

### Case Detail Card
- Citation, case name, date argued, date issued
- Lower court, appeal type, outcome badge (color-coded: green=affirm, red=reverse, orange=remand)
- One-paragraph summary
- RSA statutes at issue (clickable tags that link to RSA lookup)
- Topics/tags

### Vote Visualization
- Horizontal bar or bench diagram showing each justice's vote
- Color: blue=majority, red=dissent, gray=not participating
- For NH's 5-justice court, can display as a literal 5-seat bench diagram (à la SCOTUS app)
- Show vote count (e.g., "4-0, MacDonald disqualified")

### Opinion Text Viewer
- `st.expander("Read Full Opinion")` → renders extracted text
- Highlight RSA citations in the text

---

## Opinions Browser (`pages/01_opinions.py`)

Full searchable/filterable table of all opinions.

### Filters (sidebar)
- Year range (multi-select or slider)
- Topic tags (multi-select)
- Justice (author filter + "participated in" filter)
- Outcome (affirmed / reversed / remanded / vacated)
- Vote type (unanimous / dissent / split)
- Lower court type
- Appeal type (standard / interlocutory / certiorari)
- RSA chapter (text input)
- Party type (individual vs. state vs. business, etc.)
- AG appeared (checkbox)

### Main Table
`st.dataframe` with columns:
- Citation (sortable)
- Case Name (clickable → opens detail)
- Date Issued
- Author
- Vote
- Outcome
- Topics

### Detail Drawer
Clicking a row opens an `st.expander` or sidebar panel with the full case detail (same as Home page detail card).

---

## Justices (`pages/02_justices.py`)

Deep dive into individual justices and court-wide voting patterns.

### Tab 1: Justice Profiles

Select a justice → show:
- Appointment info (governor, date, political context)
- Total opinions authored
- Total cases participated in
- Authorship rate (% of majority opinions they wrote)
- Dissent rate (# dissents / # cases participated in)
- Most common topics in their opinions
- Timeline chart: opinions authored per year

### Tab 2: Voting Record

Select a justice + year range → show:
- Full case-by-case voting record table
- Vote breakdown pie: majority / dissent / not_participating
- Dissent list: cases where this justice dissented (with the majority lineup)
- "Lone dissenter" cases (dissented alone)

### Tab 3: Agreement Matrix

For all active justices, show pairwise agreement rate (% of cases where both justices voted the same way).

- Heatmap visualization (Plotly)
- Most-aligned pairs table
- Least-aligned pairs table (potential ideological divergence)
- Note: with only 5 justices, this is a 5x5 matrix — easy to read in full

### Tab 4: Authorship Patterns

- Bar chart: opinions authored per justice, per year
- Who authors the most unanimous opinions?
- Who authors the most dissents?
- "Per curiam" frequency over time

---

## Analysis (`pages/03_analysis.py`)

Cross-cutting analytical views. This is the meatiest section.

### Tab 1: Term Statistics

Select a year:
- Total opinions issued
- Breakdown by outcome (affirmed / reversed / etc.)
- Breakdown by topic
- Average days from argument to decision
- Longest/shortest deliberations
- Unanimous vs. divided decision ratio

### Tab 2: Statutory Spotlight

NH courts interpret statutes constantly. Surface this:
- Most-cited RSA chapters across all opinions (bar chart)
- RSA chapter search: "show all opinions citing RSA 135"
- Trend: has citation of a particular RSA chapter increased over time?
- "Statutory interpretation" flag: what % of opinions involve explicit statutory construction?
- Standard of review breakdown (de novo vs. abuse of discretion, etc.)

### Tab 3: Win Rate Analysis

Who wins at the NH Supreme Court?

- State vs. individual criminal appeals: conviction affirmed vs. reversed
- Government vs. private party: administrative appeals
- Petitioner vs. respondent overall win rates
- Win rate by lower court (do some lower courts get reversed more?)
- Win rate by topic area (which case types see more reversals?)
- Win rate trend over years

### Tab 4: Close Decisions

Cases with dissents — the court's most contested opinions:
- Timeline of dissented cases
- Which justice(s) most often in the dissent?
- Topic breakdown: which areas generate the most disagreement?
- Case list: all cases with a dissent, with the vote lineup shown

### Tab 5: Counsel Analytics

Who appears most before the court?
- Most frequent attorneys (appellant / appellee)
- Attorney win rates
- Firms by appearance count
- AG's office: win rate by topic area
- Pro se appearances (if detectable)

### Tab 6: Geographic / Court of Origin

- Which lower courts generate the most appeals?
- Reversal rate by lower court
- Map of NH counties → volume of appeals (Hillsborough, Merrimack, Rockingham, etc.)

---

## Legal Topics (`pages/04_topics.py`)

Topic-first exploration of the case law.

### Topic Overview
- Select one or more topics
- Show: case count, reversal rate, author distribution, year trend
- Filterable case list for selected topic(s)

### RSA Tracker
- Enter an RSA chapter or section
- See all opinions citing that statute
- Outcome breakdown for those opinions
- Timeline of when that statute has been litigated
- Full list of cases, sortable by date

### Statutory Interpretation Cases
- Filter to all cases where `involves_statutory_interpretation = true`
- Standard of review breakdown within this subset
- Most common RSA chapters in these cases
- Outcome distribution

### Criminal vs. Civil
- Split view: criminal appeals vs. civil
- For criminal: conviction affirmed / reversed; competency; sentencing
- For civil: administrative / insurance / family / property / contract

---

## Case Orders (`pages/05_case_orders.py`)

Non-precedential orders — useful for docket activity and procedural tracking.

- Filterable table of all case orders
- Order type distribution (what kinds of motions is the court granting/denying?)
- Activity timeline: volume of orders per week/month
- Cross-reference: does this docket number appear in the opinions list? (links pending appeals to eventual decisions)

---

## Search (`pages/06_search.py`)

Full-text search across all opinions.

- Text input → search against `full_text` field (or pre-built index)
- Returns ranked list of matching opinions with highlighted snippet
- Filters: year, topic, justice, outcome
- Implementation options:
  - Simple: Python `str.find()` across in-memory text dict (works for <500 opinions)
  - Better: `whoosh` (pure Python full-text search library)
  - Best: pre-build a `tantivy` or `sqlite FTS5` index

---

## About / Methodology (`pages/07_about.py`)

- Data source explanation (court website, PDFs)
- Parsing methodology and limitations
- Known issues (parsing errors, incomplete records)
- Justice roster with appointment history
- GitHub link
- Last updated timestamp

---

## Sidebar (Global)

Present on all pages:
- App title + NH seal logo
- Last data refresh date
- Quick stats: total opinions in database, year range covered
- Link to court website
- "Report a parsing error" link (GitHub issue template)

---

## Nice-to-Have / Phase 3 Features

- **AI Summary:** Use Claude API to generate plain-language case summaries for opinions where `summary_paragraph` is dense legalese
- **Opinion Comparison:** Side-by-side view of two opinions (e.g., compare a 2020 and 2025 ruling on the same RSA)
- **Alert / Watch:** User sets up a keyword or RSA chapter → gets notified when a new opinion matches (would require backend or email integration)
- **Citation Graph:** Which opinions cite earlier NH cases? Build a network graph of self-citations
- **Export:** Download filtered opinion list as CSV or JSON
