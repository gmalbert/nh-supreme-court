# Granite State Appeals — Enhancement Suggestions

## Priority 1: Search & Discovery

### Full-Text Opinion Search
- Add stemmed keyword search across opinion text using SQLite FTS5 (or `whoosh` for local index).
- Allow queries like "duty to warn" or "implied warranty" to surface relevant opinions.

### Case Citation Graph
- Parse opinion text for citations to other NH Supreme Court cases.
- Build a NetworkX graph of citation relationships; display as an interactive Plotly network chart.

### Similar Cases Recommender
- Using TF-IDF on topic and headnote text, find the 5 most similar past cases to any displayed opinion.

## Priority 2: Analytics

### Reversal Rate by Trial Court
- Current `pages/07_Trial_Courts.py` shows origin courts. Add reversal rate (Reversed / Total) per origin court to surface which trial courts are most frequently overturned.

### Justice Agreement Matrix
- When two justices vote together vs. apart. Heatmap showing agreement % for all 5×5 pairs.

### Time-to-Decision Analysis
- Date filed vs. date decided (where available). Identify unusually long or fast-tracked cases.

## Priority 3: Content Enhancements

### Oral Argument Transcripts
- NH Supreme Court posts transcripts online. Build a transcript viewer with keyword search.

### Decision Summary AI
- Use a local summarisation model (`sumy`, `transformers` summarisation) to generate a 2-sentence plain-language summary for each opinion.

## Priority 4: Data Pipeline

### Automated Weekly Fetch
- Extend `update_pipeline.ps1` to run on a GitHub Actions schedule and commit new opinions automatically.
- Track incremental new opinions vs. updates to existing ones.
