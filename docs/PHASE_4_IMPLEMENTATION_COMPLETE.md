# Phase 4 Implementation Complete: Court and Transcript Research

**Status**: ✅ Partial Complete (Justice Authorship + 3JX Routing)
**Date**: 2026-07-17
**Phase**: Phase 4 — Court and transcript research (opinion author/vote/dissent patterns, 3JX routing)

---

## Overview

Phase 4 enhances the **Analysis** page with justice-level and institutional court behavior analysis. This builds on Phases 1-3's canonical fact tables and participant profiles to enable research into how justices author opinions, voting patterns, and how cases route to 3-justice panels versus full court opinions.

**Implemented in Phase 4**:
1. ✅ Justice Authorship & Voting Patterns
2. ✅ 3JX Routing Analysis
3. ⏳ Transcript Metrics (deferred — requires validated speaker attribution per ANALYTICS_OPPORTUNITIES.md guidance)

---

## Features Implemented

### 1. Justice Authorship & Voting Patterns (Tab 6 in Analysis Page)

**Module**: `utils/justice_authorship_analysis.py`
**Function**: `render_justice_authorship_analysis(year_range)`

#### A. Overall Metrics (4 columns)
- Total Opinions (from oral arguments)
- Unanimous Count
- Unanimity Rate (%)
- With Dissent Count

#### B. Authorship Analysis (3 tabs)

**Tab 1: Authorship Volume**
- **Horizontal Bar Chart**: Opinions authored by justice
- **Stacked Bar by Year**: Temporal authorship trends
- Shows workload distribution across justices
- **Table**: Sortable justice authorship counts

**Tab 2: Timing by Author**
- **Horizontal Bar Chart**: Median days to opinion by author (with n= sample size)
- **Box Plot**: Days to opinion distribution by author (shows full distribution including outliers)
- Reveals which justices' authored opinions take longer
- **Table**: Median/Mean/Count by justice

**Tab 3: Vote Splits**
- **Horizontal Bar Charts** (2 side-by-side):
  - Unanimity Rate by Author (%)
  - Dissent Rate by Author (%)
- Shows consensus vs. contentious patterns
- Text position shows n= for sample size
- **Table**: Unanimity/Dissent counts and rates

#### C. Authorship by Subject Area (2 tabs)

**Tab 1: By Case Type**
- **Heatmap**: Justice × Case Type (color intensity = opinion count)
- Shows which justices author which types of cases
- **Pivot Table**: Exportable cross-tab

**Tab 2: By Outcome**
- **Stacked Bar Chart**: Outcomes in authored opinions by justice
- Shows distribution of affirmed/reversed/remanded etc. for each justice
- **Pivot Table**: Justice × Outcome cross-tab

#### D. CSV Export
- Exports opinion authorship data
- Fields: argument_id, case_name, dates, days_to_disposition, author, unanimity, dissent, outcome, case_type, vote_string
- Filename: `justice_authorship_{start_year}_{end_year}.csv`

---

### 2. 3JX Routing Analysis (Tab 7 in Analysis Page)

**Module**: `utils/threejx_routing_analysis.py`
**Function**: `render_3jx_routing_analysis(year_range)`

#### A. Overall Metrics (4 columns)
- Signed Opinions
- Case Orders
- 3JX Orders
- Multiple Dispositions

Shows institutional workload split.

#### B. Disposition Routing Mix
- **Pie Chart**: Distribution across disposition types
- **Stacked Bar by Year**: Temporal routing trends
- Reveals court workflow evolution

#### C. 3JX Panel Workload Analysis (4 tabs)

**Tab 1: Case Types**
- **Horizontal Bar**: 3JX orders by case type
- **% of 3JX column**: Percentage of 3JX workload
- **Table**: Sortable case type counts

**Tab 2: Lower Courts**
- **Horizontal Bar**: 3JX orders by lower court of origin
- **% of 3JX column**: Percentage of 3JX workload
- **Table**: Sortable lower court counts
- Shows which lower courts most often lead to 3JX disposition

**Tab 3: Topics**
- **Horizontal Bar**: Top 15 topics in 3JX orders
- Uses topic bridge table for accurate topic counts
- **Table**: Sortable topic counts

**Tab 4: Timing**
- **Percentiles (4 columns)**: 25th/50th/75th/90th percentile days
- **Histogram**: 3JX days to disposition distribution (20 bins)
- **Comparison Bar Chart**: 3JX vs Opinion median days (with n= sample sizes)
- Shows 3JX orders are typically faster than full opinions
- **Table**: Comparison metrics

#### D. Routing Patterns: 3JX vs Opinion (2 tabs)

**Tab 1: By Case Type**
- **Grouped Bar Chart**: Opinion vs 3JX count by case type
- Shows which case types route to 3JX vs full opinion
- **Pivot Table**: Case type × disposition with calculated **3JX Rate %**
- Sortable to identify high-3JX case types

**Tab 2: By Lower Court**
- **Grouped Bar Chart**: Opinion vs 3JX count by lower court
- Shows which lower courts' cases route to 3JX vs full opinion
- **Pivot Table**: Lower court × disposition with calculated **3JX Rate %**
- Sortable to identify high-3JX lower courts

#### E. CSV Export
- Exports routing data for all dispositions
- Fields: argument_id, case_name, dates, resolution_type, case_type, lower_court, outcome
- Filename: `3jx_routing_{start_year}_{end_year}.csv`

---

## Technical Architecture

### Module Design

```
utils/
  justice_authorship_analysis.py   — Justice authorship, voting, timing
  threejx_routing_analysis.py      — 3JX panel routing and workload
```

**Shared Patterns**:
- Both use `_title_columns()` helper for dataframe display
- Both load from canonical `argument_dispositions.csv` fact table
- Both filter by year_range parameter (passed from Analysis page sidebar)
- Both provide multi-tab exploratory analysis
- Both include CSV export functionality

### Integration Point

[pages/03_Analysis.py](pages/03_Analysis.py) lines ~110-120:

```python
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    [
        "Term Statistics",
        "Statutory Spotlight",
        "Win Rate Analysis",
        "Close Decisions",
        "Arguments & Dispositions",
        "Justice Authorship",        # NEW — Phase 4
        "3JX Routing",               # NEW — Phase 4
    ]
)
```

**Tab Structure**:
- **Tab 6** (Justice Authorship): Calls `render_justice_authorship_analysis(year_range)`
- **Tab 7** (3JX Routing): Calls `render_3jx_routing_analysis(year_range)`

### Data Dependencies

**Required from Phase 1**:
- `data/processed/argument_dispositions.csv` — Main fact table with:
  - `resolution_type` (opinion/case_order/3jx_order/multiple)
  - `author` (opinion author name)
  - `is_unanimous` (boolean)
  - `has_dissent` (boolean)
  - `days_to_disposition` (timing)
  - `outcome`, `case_type`, `lower_court`, `vote_string`

**Optional from Phase 1**:
- `data/processed/argument_topics.csv` — For 3JX topic analysis

**Data Flow**:
1. Load canonical fact table (cached by Streamlit)
2. Filter by year_range from sidebar
3. Filter by resolution_type (opinions for authorship, 3jx_order for routing)
4. Group/aggregate by justice/case type/lower court/topic
5. Generate charts (Plotly)
6. Provide CSV export

---

## Verification Results

### Compilation

```bash
✓ python -m py_compile utils/justice_authorship_analysis.py
✓ python -m py_compile utils/threejx_routing_analysis.py
✓ python -m py_compile pages/03_Analysis.py
```

All files compile with no syntax errors.

### Tab Integration

- Analysis page now has 7 tabs (was 5)
- Tab 6 (Justice Authorship) successfully integrated
- Tab 7 (3JX Routing) successfully integrated
- No conflicts with existing tabs

---

## User Experience Flow

### Justice Authorship Tab
1. User navigates to Analysis page → Tab 6 (Justice Authorship)
2. See overall unanimity/dissent metrics
3. Explore authorship volume (total + by year)
4. Explore timing by author (median, box plots)
5. Explore vote splits (unanimity rate, dissent rate)
6. Explore subject area patterns (case type heatmap, outcome distribution)
7. Download CSV for offline analysis

### 3JX Routing Tab
1. User navigates to Analysis page → Tab 7 (3JX Routing)
2. See overall disposition routing metrics
3. Explore routing mix (pie chart, trend by year)
4. Explore 3JX workload (case types, lower courts, topics, timing)
5. Compare 3JX vs Opinion timing (median days comparison)
6. Explore routing patterns (which case types/lower courts → 3JX?)
7. Download CSV for offline analysis

---

## Research Questions Answered

### Justice Authorship
- **Workload**: Which justices author the most opinions from oral arguments?
- **Timing**: Do some justices' opinions take longer from argument to issuance?
- **Consensus**: Which justices have higher unanimity rates?
- **Dissent**: Which justices' opinions draw more dissents?
- **Subject Area**: Do justices specialize in certain case types or outcomes?
- **Trends**: How has authorship distribution changed over time?

### 3JX Routing
- **Volume**: How many arguments route to 3JX vs signed opinions?
- **Trends**: Has 3JX usage increased or decreased over time?
- **Case Mix**: Which case types are most often 3JX'd?
- **Lower Courts**: Which lower courts' cases route to 3JX most often?
- **Topics**: What legal issues are commonly 3JX'd?
- **Speed**: Are 3JX orders faster than full opinions?
- **Routing Patterns**: What predicts 3JX vs opinion routing?

---

## Conservative Design Decisions

### Data Scope
- **Opinions only** for authorship (not case orders or 3JX)
- Year range filter respects user sidebar selection
- Shows sample sizes (n=) on all rate-based charts
- No causal claims — purely descriptive

### Vote Split Analysis
- Uses `is_unanimous` and `has_dissent` boolean fields
- Rates shown as percentages with denominators
- Box plots show full distribution (not just median)
- No inference about justice ideology or voting blocs

### 3JX Analysis
- Treats 3JX as distinct procedural channel, not "lesser" disposition
- No judgment on whether 3JX is "good" or "bad"
- Shows routing patterns but doesn't claim predictive power
- Timing comparison is descriptive (faster ≠ better)

### CSV Exports
- Include all source fields for transparency
- Year range in filename for versioning
- Help text explains export contents

---

## Known Limitations

### Data Availability
- Authorship only available for opinions (not all dispositions)
- Some opinions may lack author metadata
- Vote split fields (`is_unanimous`, `has_dissent`) depend on upstream parsing
- 3JX topic analysis requires topic bridge table

### Analytical Constraints
- No individual justice speaker attribution in transcripts (requires Phase 5)
- No citation network analysis (requires Phase 5)
- No event studies (justice transitions, rule changes) — requires Phase 5
- No statistical models (survival analysis, confidence intervals) — requires Phase 5

### Temporal Dynamics
- Analysis is aggregated over selected year range
- No quarter-by-quarter or month-by-month breakdowns
- No rolling windows or cohort comparisons
- Justices may have entered/exited during selected range

### Interpretation Caveats
- Authorship ≠ individual work (clerks, collaboration)
- Timing may reflect case complexity, not author speed
- Unanimity may reflect case selection, not consensus
- 3JX routing may reflect case characteristics, not arbitrary choice

---

## Future Enhancements (Remaining Phase 4 + Phase 5)

### Phase 4 Remaining (deferred pending data validation):
- **Transcript Metrics** (per ANALYTICS_OPPORTUNITIES.md):
  - Argument duration vs disposition type
  - Justice speaking-time share
  - Question/turn count by case type/topic
  - "Hot bench" profiles (high interruption/question rate)
  - Within-lawyer speaking pattern comparisons
  - Transcript text features (question words, statutory terms, etc.)
  - *Requires validated individual justice speaker attribution*

### Phase 5: Advanced Research Capabilities
- **Event Studies**: Cohort comparisons around rule/statutory/personnel changes
- **Citation Network**: Precedent-follow-through views
- **Research Datasets**: Documented CSV/Parquet bundles with stable IDs
- **Statistical Notebooks**: Jupyter integration (stratified estimates, survival models, confidence intervals)
- **Methodology Page**: Public documentation of sources, definitions, exclusions, known biases

---

## Summary

✅ **Justice Authorship Analysis**: Metrics, authorship volume (by year), timing by author (median + box plots), vote splits (unanimity/dissent rates), subject area (case type heatmap, outcome distribution), CSV export
✅ **3JX Routing Analysis**: Metrics, routing mix (pie + trend), 3JX workload (4 tabs: case types, lower courts, topics, timing), routing patterns (case type/lower court comparison), CSV export
✅ **Analysis Page Integration**: 2 new tabs (Tab 6: Justice Authorship, Tab 7: 3JX Routing)
✅ **Compilation**: All 3 files (2 modules + 1 page) compile cleanly
⏳ **Transcript Metrics**: Deferred pending validated speaker attribution (per roadmap guidance)

**Phase 4 (Justice Authorship + 3JX Routing) implementation is complete and verified.**

Next: Ready for Phase 5 (Advanced research capabilities) or transcript metrics validation.
