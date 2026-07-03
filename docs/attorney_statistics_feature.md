# Attorney & Firm Statistics Feature - Complete Implementation

## Overview
Comprehensive attorney and law firm statistics showing who appears before the NH Supreme Court, how often they argue, duration patterns, activity over time, and detailed profiles.

## Implementation

### 1. Data Extraction Script (Enhanced)
**File:** `scripts/extract_attorney_stats.py`

Processes all 1,071 metadata.json files AND oral_arguments.json to extract:
- **Attorney names** and associated firms
- **Argument counts** per attorney
- **Duration data** (total hours, average minutes per argument)
- **Temporal data** (first/last argument dates, year-by-year breakdown)
- **Case lists** per attorney
- **Side representation** (state, defendant, plaintiff, etc.)
- **Firm statistics** (arguments, attorneys, duration, activity timeline)

**Output:** `data/processed/oral_arguments_attorney_stats.json` (enriched with duration/temporal data)

**Key Findings:**
- 1,070 cases with attorney data
- 328 unique attorneys
- 130 unique firms
- Top attorney: Elizabeth C. Woodcock (157 arguments)
- Top firm: NH Attorney General (769 arguments, 100 attorneys)

### 2. Data Loader Function
**File:** `utils/data_loader.py`

Added `load_attorney_statistics()` function:
- Returns dict with three keys:
  - `case_attorneys`: case_number → list of attorneys with firm/role/side
  - `attorney_stats`: sorted list of attorney statistics (enriched with duration/temporal data)
  - `firm_stats`: sorted list of firm statistics (enriched with duration/temporal data)
- Cached with @st.cache_data (1-hour TTL)

### 3. Attorneys & Firms Tab (Enhanced)
**File:** `pages/08_Oral_Arguments.py` → `_render_attorney_statistics()`

Added comprehensive tab with multiple sections:

#### Most Active Attorneys Section
- **Horizontal bar chart:** Top 15 attorneys by argument count
- **Expandable table:** Full list of all 328 attorneys with clickable profile links 🔍

#### Most Active Law Firms Section
- **Horizontal bar chart:** Top 15 firms by argument count
- **Expandable table:** Full list of all 130 firms with clickable profile links 🔍

#### Distribution Analysis
- **Attorney distribution:** How many attorneys have 1, 2-4, 5-9, 10-19, 20-49, or 50+ arguments
- **Firm distribution:** How many firms have argued different volumes of cases

#### Duration Analysis ✨ NEW
- **Total time chart:** Top 15 attorneys by total argument time (hours)
- **Average duration chart:** Top 15 attorneys by average argument length (minutes, min 5 cases)

#### Activity Over Time ✨ NEW
- **Timeline chart:** Top 10 attorneys' argument counts by year (2015-2026)
- Shows participation trends and career arcs

### 4. Attorney Detail Pages ✨ NEW
**File:** `pages/09_Attorney_Detail.py`

Individual attorney profile pages showing:
- **Header:** Attorney name and firm affiliation
- **Key metrics:** Total arguments, total time, avg duration, active period
- **Side representation pie chart:** Breakdown of which side they represented
- **Activity timeline bar chart:** Arguments by year
- **Complete case list:** All arguments with docket, case name, date, duration, word count
- **Back navigation:** Link back to Attorneys & Firms

**Access:** Click 🔍 icon next to attorney name in Attorneys & Firms tab

### 5. Firm Detail Pages ✨ NEW
**File:** `pages/10_Firm_Detail.py`

Individual firm profile pages showing:
- **Header:** Firm name and attorney count
- **Key metrics:** Total arguments, unique attorneys, total time, active period
- **Attorneys roster table:** All attorneys from this firm with their stats + profile links
- **Activity timeline bar chart:** Firm arguments by year
- **Complete case list:** All arguments with attorney names, dates, durations
- **Back navigation:** Link back to Attorneys & Firms

**Access:** Click 🔍 icon next to firm name in Attorneys & Firms tab

### 6. Individual Argument Pages (Enhanced) ✨ NEW
**File:** `pages/08_Oral_Arguments.py` → `_render_reader()`

Added **Attorneys section** to each oral argument page:
- **Grouped by side:** State, Defendant, Plaintiff, etc.
- **Attorney names:** Bold with firm in parentheses
- **Career stats:** Shows total career arguments and average duration for each attorney
- **Example:** "**Elizabeth C. Woodcock** (NH Attorney General) — 157 career arguments (avg 32 min)"

## Enhanced Data Schema

### Attorney Stats Structure (Enhanced)
```json
{
  "attorney_name": "Elizabeth C. Woodcock",
  "firm": "NH Attorney General",
  "total_arguments": 157,
  "cases": ["2017-0048", "2017-0265", ...],
  "total_duration_seconds": 302400,
  "total_duration_hours": 84.0,
  "average_duration_seconds": 1926,
  "average_duration_minutes": 32.1,
  "years_active": {
    "2015": 12,
    "2016": 18,
    "2017": 22,
    ...
  },
  "first_argument_date": "2015-02-11",
  "last_argument_date": "2026-04-15",
  "sides": {
    "state": 157,
    "defendant": 0,
    "plaintiff": 0,
    "appellee": 0,
    "appellant": 0,
    "other": 0
  }
}
```

### Firm Stats Structure (Enhanced)
```json
{
  "firm_name": "NH Attorney General",
  "total_arguments": 769,
  "unique_attorneys": 100,
  "attorneys": ["Elizabeth C. Woodcock", "Sean R. Locke", ...],
  "cases": ["2017-0048", "2017-0265", ...],
  "total_duration_seconds": 1512000,
  "total_duration_hours": 420.0,
  "average_duration_seconds": 1965,
  "average_duration_minutes": 32.75,
  "years_active": {
    "2015": 65,
    "2016": 82,
    ...
  },
  "first_argument_date": "2015-01-07",
  "last_argument_date": "2026-05-19"
}
```

## Key Insights

### Top Attorneys (2015-2026)
1. **Elizabeth C. Woodcock** (NH AG): 157 arguments
2. **Christopher M. Johnson** (NH Appellate Defender): 130 arguments
3. **Thomas A. Barnard** (NH Appellate Defender): 81 arguments
4. **Stephanie C. Hausman** (NH Appellate Defender): 74 arguments
5. **Sean R. Locke** (NH AG): 65 arguments

### Top Firms (2015-2026)
1. **NH Attorney General**: 769 arguments (100 attorneys)
2. **NH Appellate Defender**: 390 arguments (25 attorneys)
3. **MM** (private firm): 28 arguments (9 attorneys)
4. **S&G** (private firm): 24 arguments (8 attorneys)
5. **PPE&C** (private firm): 22 arguments (5 attorneys)

### Duration Patterns
- **Longest average arguments:** Certain attorneys consistently argue longer cases
- **Attorney specialization:** Some attorneys focus on specific case types with characteristic durations
- **Firm patterns:** NH AG and Appellate Defender have similar average durations (~32-33 min)

### Activity Trends (2015-2026)
- **Consistent participants:** Top attorneys show sustained activity over multiple years
- **Career arcs visible:** New attorneys emerging, senior attorneys retiring
- **Volume changes:** Some years have more arguments than others

### Distribution Patterns
- **Most attorneys** (>200) have argued 1-4 cases
- **Small group** (~20 attorneys) have argued 20+ cases
- **Government attorneys** dominate (AG + Appellate Defender = 1,159 arguments)
- **Private firms** typically handle fewer cases each

## Usage

### To Regenerate Statistics:
```bash
python scripts/extract_attorney_stats.py
```

### In Streamlit App:

#### View All Attorneys & Firms
1. Navigate to **Oral Arguments** page
2. Click **"Attorneys & Firms"** tab
3. View charts, expand tables, click 🔍 for profiles

#### View Individual Attorney Profile
1. From Attorneys & Firms tab, click 🔍 next to attorney name
2. Or navigate directly: `/Attorney_Detail?attorney=Elizabeth+C.+Woodcock`

#### View Individual Firm Profile
1. From Attorneys & Firms tab, click 🔍 next to firm name
2. Or navigate directly: `/Firm_Detail?firm=NH+Attorney+General`

#### See Attorneys on Argument Pages
1. Navigate to any oral argument
2. Scroll to **Attorneys** section
3. See grouped list with career stats

## Feature Completeness

✅ **All requested features implemented:**
1. ✅ Attorney/firm data extracted and parsed
2. ✅ Duration/length analysis by attorney (total hours, avg minutes)
3. ✅ Attorney information on individual argument pages
4. ✅ Time trend analysis (activity over years)
5. ✅ Attorney detail pages (individual profiles)
6. ✅ Firm detail pages (bonus)
7. ✅ Clickable navigation throughout

## Files Modified/Created

### New Files
1. `pages/09_Attorney_Detail.py` - Individual attorney profiles
2. `pages/10_Firm_Detail.py` - Individual firm profiles

### Modified Files
1. `scripts/extract_attorney_stats.py` - Enhanced with duration/temporal extraction
2. `utils/data_loader.py` - Added `load_attorney_statistics()`
3. `pages/08_Oral_Arguments.py` - Enhanced with:
   - Duration analysis charts
   - Time trend visualizations
   - Attorney info on argument pages
   - Clickable profile links
4. `data/processed/oral_arguments_attorney_stats.json` - Enriched output file

## Future Enhancements (Optional)

Possible future additions:
- **Win rate analysis** (requires outcome data linkage)
- **Topic specialization** (which attorneys handle which legal topics)
- **Network visualization** (attorney-firm-case relationships)
- **Geographic analysis** (firm locations, if available)
- **Co-counsel patterns** (which attorneys argue together)
- **Justice interaction patterns** (which attorneys get more questions from specific justices)
- **Transcript analysis** (speaking style, word choice patterns)

## Technical Notes

- Attorney data sourced from metadata.json files in transcript archive
- Duration data merged from oral_arguments.json
- Some cases may have incomplete attorney data
- Firm names are sometimes abbreviated (MM, S&G, etc.)
- Side classification is based on metadata labels
- URL encoding handles attorney/firm names with spaces and special characters
- All visualizations use Plotly for interactivity
- Tables use st.column_config for clickable links and proper formatting
