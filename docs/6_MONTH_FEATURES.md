# Granite State Appeals — 6-Month Feature Roadmap

## Month 1: Search & Navigation

- **Keyword search bar** — Full-text search across all opinions by keyword or phrase.
- **Docket number lookup** — Direct docket number input field for instant case retrieval.
- **Recent decisions ticker** — Show the last 10 opinions decided, auto-updated by the pipeline.
- **Filters on Cases page** — Filter by disposition, topic, year, and author.

## Month 2: Justice Profiles

- **Justice profile page** — Tenure chart, opinion count, reversal rate, top topics written.
- **Voting record matrix** — Agreement heatmap for all current and recent justices.
- **Authored opinions list** — Filterable list of every opinion by a selected justice.

## Month 3: Analytics Dashboards

- **Reversal rate by trial court** — Bar chart showing which lower courts are most frequently reversed.
- **Topic trend chart** — How the mix of legal topics has changed by year.
- **Decision timing analysis** — Average days from argument to decision by topic area.

## Month 4: Case Deep-Dive

- **Plain-language summary** — 2-sentence auto-summary for each opinion.
- **Cited cases links** — In-opinion citation parsing; link to other NH Supreme Court cases cited.
- **Download opinion PDF** — Direct link to the official NH Courts PDF.

## Month 5: Comparison & Reporting

- **Compare cases tool** — Select two cases; display side-by-side topics, justices, and outcomes.
- **Annual report generator** — PDF summary of the court's year: total opinions, reversal rate, busiest topics.
- **Bookmark / favourites** — Session-state bookmarks for frequently referenced cases.

## Month 6: Automation

- **Weekly pipeline** — GitHub Action runs `update_pipeline.ps1` every Monday.
- **New opinion alert** — Email notification when a new opinion is added in a tracked topic area.
- **Webhook** — POST to a Discord webhook with each new opinion summary.
