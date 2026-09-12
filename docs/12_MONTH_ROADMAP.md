# NH Supreme Court (Granite State Appeals) — 12-Month Feature Roadmap

> Generated: 2026-07-31 | Horizon: August 2026 – July 2027

---

## Executive Summary

This roadmap evolves Granite State Appeals from a case-browsing platform into
a comprehensive NH legal intelligence platform with predictive outcome modeling,
attorney analytics, argument transcript search, semantic case similarity, and
judge profile deep dives.

---

## Q1 (Aug–Oct 2026) — AI Search & Semantic Intelligence

### Feature 1 — Semantic Case Search (Vector Embeddings)

Embed all NH Supreme Court opinions using sentence-transformers. Enable
natural language search: "cases about landlord-tenant disputes in 2024."

```python
# utils/semantic_search.py
import numpy as np, pandas as pd
from pathlib import Path
import json
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDINGS_FILE = Path("data_files/opinion_embeddings.npz")

def build_opinion_embeddings(opinions: pd.DataFrame) -> None:
    """Generate and cache sentence embeddings for all opinions."""
    model = SentenceTransformer(MODEL_NAME)
    texts = (opinions["docket_number"] + " | " +
             opinions["case_name"].fillna("") + " | " +
             opinions["topic"].fillna("") + " | " +
             opinions["summary"].fillna("")).tolist()
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=32)
    np.savez_compressed(EMBEDDINGS_FILE, embeddings=embeddings,
                        docket_numbers=opinions["docket_number"].values)
    print(f"Saved {len(embeddings)} embeddings to {EMBEDDINGS_FILE}")

def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    """Return top-k opinions most similar to the query."""
    model = SentenceTransformer(MODEL_NAME)
    data = np.load(EMBEDDINGS_FILE, allow_pickle=True)
    embeddings = data["embeddings"]
    docket_nums = data["docket_numbers"]

    query_emb = model.encode([query])[0]
    scores = np.dot(embeddings, query_emb) / (
        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_emb) + 1e-8
    )
    top_idx = np.argsort(scores)[-top_k:][::-1]
    return [{"docket": docket_nums[i], "score": float(scores[i])} for i in top_idx]
```

### Feature 2 — Outcome Prediction Model

Train a logistic regression / random forest predicting affirm vs reverse
disposition given: topic, appellant type, panel composition, length, term.

```python
# utils/ml_predictor.py
import pandas as pd, numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
import joblib
from pathlib import Path

FEATURES = [
    "topic_encoded", "appellant_type_encoded",
    "panel_composition_hash", "year", "term_month",
    "case_length_chars", "num_prior_cases_cited",
    "is_criminal_appeal", "is_administrative_appeal",
    "judge_author_encoded",
]

def train_outcome_model(df: pd.DataFrame) -> None:
    df = df.copy()
    le = LabelEncoder()
    for col in ["topic", "appellant_type", "judge_author"]:
        df[f"{col}_encoded"] = le.fit_transform(df[col].fillna("unknown"))

    X = df[[f for f in FEATURES if f in df.columns]].fillna(0)
    y = (df["disposition"] == "Affirmed").astype(int)

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    aucs = []
    model = GradientBoostingClassifier(n_estimators=300, max_depth=3)
    for tr, val in skf.split(X, y):
        model.fit(X.iloc[tr], y.iloc[tr])
        preds = model.predict_proba(X.iloc[val])[:, 1]
        aucs.append(roc_auc_score(y.iloc[val], preds))
    print(f"Outcome model AUC: {np.mean(aucs):.3f} ± {np.std(aucs):.3f}")
    model.fit(X, y)
    joblib.dump(model, Path("data_files/outcome_model.joblib"))
```

### Feature 3 — Legal Topic Taxonomy Auto-Labeler

Use a zero-shot classification model to automatically tag incoming opinions
with legal topics from a predefined NH-specific taxonomy.

```python
# utils/topic_labeler.py
from transformers import pipeline
import pandas as pd

NH_LEGAL_TOPICS = [
    "Criminal Law", "Family Law", "Contract Disputes", "Property Rights",
    "Administrative Law", "Personal Injury", "Constitutional Rights",
    "Workers Compensation", "Insurance", "Landlord-Tenant",
    "DUI/DWI", "Juvenile Justice", "Professional Malpractice",
    "Estate Law", "Zoning and Land Use",
]

def auto_label_topic(text: str, threshold: float = 0.30) -> list[str]:
    """Zero-shot classify opinion text into topic(s)."""
    classifier = pipeline("zero-shot-classification",
                           model="facebook/bart-large-mnli")
    result = classifier(
        text[:512],  # truncate for speed
        candidate_labels=NH_LEGAL_TOPICS,
        multi_label=True,
    )
    return [label for label, score in zip(result["labels"], result["scores"])
            if score >= threshold]

def batch_label_opinions(df: pd.DataFrame, text_col: str = "opinion_text") -> pd.DataFrame:
    df = df.copy()
    df["auto_topics"] = df[text_col].apply(
        lambda t: auto_label_topic(t[:512]) if pd.notna(t) else []
    )
    return df
```

### Feature 4 — Oral Argument Audio Search

Index all oral argument audio/transcripts. Enable keyword search across
argument transcripts. Link to timestamped audio clips.

```python
# utils/transcript_search.py
import pandas as pd
from pathlib import Path
import json, re

TRANSCRIPTS_DIR = Path("data_files/transcripts")

def build_transcript_index(transcripts_dir: Path = TRANSCRIPTS_DIR) -> pd.DataFrame:
    """Build searchable index from all transcript JSON files."""
    rows = []
    for f in transcripts_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            for segment in data.get("segments", []):
                rows.append({
                    "docket": data.get("docket_number", f.stem),
                    "speaker": segment.get("speaker", ""),
                    "text": segment.get("text", ""),
                    "start_sec": segment.get("start", 0),
                    "end_sec": segment.get("end", 0),
                })
        except Exception:
            continue
    return pd.DataFrame(rows)

def search_transcripts(
    query: str, index: pd.DataFrame, case_filter: str | None = None
) -> pd.DataFrame:
    """Search transcript segments for a keyword or phrase."""
    if case_filter:
        index = index[index["docket"] == case_filter]
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    mask = index["text"].str.contains(pattern, na=False)
    results = index[mask].copy()
    results["context"] = results["text"].apply(
        lambda t: t[:200] + "..." if len(t) > 200 else t
    )
    return results[["docket", "speaker", "context", "start_sec"]]
```

### Feature 5 — Case Citation Network Graph

Build a directed citation network: case A cites case B. Identify highly-cited
"landmark" precedents. Visualize with NetworkX + Plotly.

```python
# utils/citation_network.py
import pandas as pd, re
import networkx as nx
import plotly.graph_objects as go

def extract_citations(text: str) -> list[str]:
    """Extract NH Supreme Court docket numbers cited in opinion text."""
    pattern = r'\b\d{4}-\d{4}\b'
    return re.findall(pattern, text or "")

def build_citation_graph(opinions: pd.DataFrame) -> nx.DiGraph:
    G = nx.DiGraph()
    for _, row in opinions.iterrows():
        docket = row["docket_number"]
        G.add_node(docket, case_name=row.get("case_name", ""),
                   year=row.get("date_decided", "")[:4] if row.get("date_decided") else "")
        cited = extract_citations(row.get("opinion_text", ""))
        for c in cited:
            if c != docket and c in opinions["docket_number"].values:
                G.add_edge(docket, c)
    return G

def render_citation_graph(G: nx.DiGraph, top_n: int = 50) -> go.Figure:
    # Only visualize top N most-cited cases
    top_nodes = sorted(G.nodes(), key=lambda n: G.in_degree(n), reverse=True)[:top_n]
    sub = G.subgraph(top_nodes)
    pos = nx.spring_layout(sub, seed=42)

    edge_trace = go.Scatter(
        x=sum([[pos[u][0], pos[v][0], None] for u, v in sub.edges()], []),
        y=sum([[pos[u][1], pos[v][1], None] for u, v in sub.edges()], []),
        mode="lines", line=dict(color="rgba(150,150,255,0.3)", width=1),
        showlegend=False,
    )
    node_trace = go.Scatter(
        x=[pos[n][0] for n in sub.nodes()],
        y=[pos[n][1] for n in sub.nodes()],
        mode="markers+text",
        text=[n for n in sub.nodes()],
        textposition="top center",
        marker=dict(
            size=[max(5, sub.in_degree(n) * 3) for n in sub.nodes()],
            color=[sub.in_degree(n) for n in sub.nodes()],
            colorscale="Viridis", showscale=True,
        ),
        showlegend=False,
    )
    return go.Figure(data=[edge_trace, node_trace],
                     layout=go.Layout(title="NH Supreme Court Citation Network",
                                      template="plotly_dark", showlegend=False))
```

---

## Q2 (Nov 2026 – Jan 2027) — Attorney & Judge Analytics

### Feature 6 — Attorney Win Rate Dashboard

Track each attorney's win rate before the NH Supreme Court by topic,
by panel, and over time. Surface patterns in appellate advocacy effectiveness.

```python
# pages/attorney_analytics.py
import streamlit as st, pandas as pd, plotly.express as px

def render_attorney_dashboard(opinions: pd.DataFrame) -> None:
    st.title("⚖️ Attorney Analytics Dashboard")
    attorneys = sorted(set(
        opinions["appellant_attorney"].dropna().tolist() +
        opinions["appellee_attorney"].dropna().tolist()
    ))
    selected = st.selectbox("Select Attorney", attorneys)

    # Appellant cases
    app_cases = opinions[opinions["appellant_attorney"] == selected].copy()
    app_cases["won"] = (app_cases["disposition"] == "Reversed").astype(int)

    # Appellee cases
    apl_cases = opinions[opinions["appellee_attorney"] == selected].copy()
    apl_cases["won"] = (apl_cases["disposition"] == "Affirmed").astype(int)

    all_cases = pd.concat([app_cases, apl_cases])

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Cases", len(all_cases))
    col2.metric("Win Rate", f"{all_cases['won'].mean():.1%}")
    col3.metric("Unique Topics", all_cases["topic"].nunique())

    if len(all_cases) > 0:
        by_topic = all_cases.groupby("topic")["won"].agg(["mean", "count"]).reset_index()
        fig = px.bar(by_topic.sort_values("mean", ascending=False),
                     x="topic", y="mean", color="count",
                     title=f"Win Rate by Topic — {selected}",
                     template="plotly_dark")
        st.plotly_chart(fig, width="stretch")
```

### Feature 7 — Justice Voting Pattern Heatmap

Display a justice × topic voting pattern matrix. Show each justice's
ruling tendencies (pro-appellant, pro-appellee) per legal topic.

```python
# pages/justice_analytics.py
import streamlit as st, pandas as pd, plotly.express as px

def render_justice_voting_heatmap(opinions: pd.DataFrame) -> None:
    st.title("⚖️ Justice Voting Patterns")
    # Expand justice votes (stored as list in panel field)
    vote_rows = []
    for _, row in opinions.iterrows():
        for justice in row.get("panel", []):
            vote_rows.append({
                "justice": justice,
                "topic": row.get("topic", "Unknown"),
                "pro_appellant": int(row.get("disposition", "") in ["Reversed", "Vacated"]),
            })
    votes_df = pd.DataFrame(vote_rows)
    if votes_df.empty:
        st.info("No voting data available.")
        return

    pivot = votes_df.pivot_table(
        index="justice", columns="topic", values="pro_appellant",
        aggfunc="mean", fill_value=0.5
    )
    fig = px.imshow(pivot, color_continuous_scale="RdYlGn",
                    zmin=0, zmax=1,
                    title="Pro-Appellant Rate by Justice and Topic",
                    template="plotly_dark", text_auto=".2f")
    st.plotly_chart(fig, width="stretch")
```

### Feature 8 — Case Outcome Prediction Widget

For any new case description, predict probability of affirmance/reversal.
Display SHAP feature importance explaining the prediction.

```python
# pages/outcome_predictor.py
import streamlit as st, pandas as pd, numpy as np, shap, joblib
from pathlib import Path
from sklearn.preprocessing import LabelEncoder

def render_outcome_predictor(opinions: pd.DataFrame) -> None:
    st.title("🔮 Case Outcome Predictor")
    st.caption("Enter case details to estimate likely outcome.")

    topic = st.selectbox("Legal Topic", sorted(opinions["topic"].dropna().unique()))
    appellant_type = st.selectbox("Appellant Type", ["Individual", "Business", "Government", "Other"])
    year = st.number_input("Year", 2000, 2030, 2026)
    is_criminal = st.checkbox("Criminal Appeal")

    if st.button("Predict"):
        model = joblib.load(Path("data_files/outcome_model.joblib"))
        X = pd.DataFrame([{
            "topic_encoded": hash(topic) % 100,
            "appellant_type_encoded": {"Individual": 0, "Business": 1, "Government": 2, "Other": 3}[appellant_type],
            "year": year,
            "is_criminal_appeal": int(is_criminal),
        }])
        prob_affirm = model.predict_proba(X)[0][1]
        col1, col2 = st.columns(2)
        col1.metric("P(Affirmed)", f"{prob_affirm:.1%}")
        col2.metric("P(Reversed/Vacated)", f"{1-prob_affirm:.1%}")
        pred = "AFFIRMED" if prob_affirm > 0.5 else "REVERSED"
        st.info(f"Model predicts: **{pred}** with {max(prob_affirm, 1-prob_affirm):.1%} confidence")
```

### Feature 9 — Historical Data Download & API

Expose NH Supreme Court data as a downloadable dataset (CSV/JSON) and
a simple REST API for researchers and developers.

```python
# api/nh_courts_api.py
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from utils.data_loader import load_opinions
import pandas as pd

app = FastAPI(title="Granite State Appeals API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])

@app.get("/opinions")
def get_opinions(
    year: int | None = None,
    topic: str | None = None,
    disposition: str | None = None,
    limit: int = Query(50, le=500),
) -> list[dict]:
    df = load_opinions()
    if year:
        df = df[pd.to_datetime(df["date_decided"]).dt.year == year]
    if topic:
        df = df[df["topic"].str.contains(topic, case=False, na=False)]
    if disposition:
        df = df[df["disposition"].str.lower() == disposition.lower()]
    return df.head(limit).to_dict("records")

@app.get("/opinions/{docket_number}")
def get_opinion(docket_number: str) -> dict:
    df = load_opinions()
    row = df[df["docket_number"] == docket_number]
    if row.empty:
        from fastapi import HTTPException
        raise HTTPException(404, "Opinion not found")
    return row.iloc[0].to_dict()

@app.get("/stats/topics")
def get_topic_stats() -> list[dict]:
    df = load_opinions()
    return df.groupby("topic").size().reset_index(name="count").to_dict("records")
```

### Feature 10 — NH Legal Calendar & Filing Deadline Tracker

Import NH court calendar and display upcoming oral arguments, conference
dates, and important deadlines.

```python
# utils/court_calendar.py
import requests, pandas as pd
from bs4 import BeautifulSoup

NH_COURT_CAL_URL = "https://www.courts.nh.gov/supreme-court/oral-arguments"

def fetch_oral_argument_schedule() -> pd.DataFrame:
    """Scrape upcoming NH Supreme Court oral arguments."""
    resp = requests.get(NH_COURT_CAL_URL,
                        headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    soup = BeautifulSoup(resp.text, "lxml")
    rows = []
    for row in soup.find_all("tr")[1:]:  # skip header
        cells = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cells) >= 3:
            rows.append({
                "date": cells[0],
                "docket": cells[1],
                "case_name": cells[2],
                "time": cells[3] if len(cells) > 3 else "9:00 AM",
            })
    return pd.DataFrame(rows)
```

---

## Q3 (Feb–Apr 2027) — Enhanced Analytics

### Feature 11 — Readability Score for Opinions

Compute Flesch-Kincaid readability and average sentence length for
all opinions. Track which justices write most readable decisions.

```python
# utils/readability.py
import textstat, pandas as pd

def compute_readability(text: str) -> dict:
    if not text or len(text) < 100:
        return {}
    return {
        "flesch_reading_ease": textstat.flesch_reading_ease(text),
        "flesch_kincaid_grade": textstat.flesch_kincaid_grade(text),
        "fog_index": textstat.gunning_fog(text),
        "avg_sentence_length": textstat.avg_sentence_length(text),
        "word_count": textstat.lexicon_count(text),
    }

def add_readability_scores(df: pd.DataFrame, text_col: str = "opinion_text") -> pd.DataFrame:
    scores = df[text_col].apply(
        lambda t: compute_readability(t or "")
    )
    return pd.concat([df, pd.DataFrame(scores.tolist())], axis=1)
```

### Feature 12 — Disposition Trend Analysis

Show how the NH Supreme Court's affirmance/reversal rates have changed
over time by topic. Surface increasing or decreasing trend in any area.

```python
# pages/disposition_trends.py
import streamlit as st, pandas as pd, plotly.express as px

def render_disposition_trends(opinions: pd.DataFrame) -> None:
    st.title("📈 Disposition Trends Over Time")
    opinions = opinions.copy()
    opinions["year"] = pd.to_datetime(opinions["date_decided"]).dt.year.astype("Int64")
    opinions["affirmed"] = (opinions["disposition"] == "Affirmed").astype(int)

    # Overall trend
    yearly = opinions.groupby("year")["affirmed"].agg(["mean", "count"]).reset_index()
    fig = px.line(yearly, x="year", y="mean",
                  title="Annual Affirmance Rate", template="plotly_dark",
                  labels={"mean": "Affirmance Rate"})
    fig.add_hline(y=yearly["mean"].mean(), line_dash="dash",
                  annotation_text="Avg")
    st.plotly_chart(fig, width="stretch")

    # By topic
    topic = st.selectbox("Topic", sorted(opinions["topic"].dropna().unique()))
    topic_df = opinions[opinions["topic"] == topic].groupby("year")["affirmed"].mean().reset_index()
    fig2 = px.bar(topic_df, x="year", y="affirmed",
                  title=f"Affirmance Rate — {topic}",
                  template="plotly_dark")
    st.plotly_chart(fig2, width="stretch")
```

### Feature 13 — Majority / Dissent Voting Alignment Calculator

For each pair of justices, compute how often they agree (both in majority,
both in dissent). Build a justice agreement matrix.

```python
# utils/justice_alignment.py
import pandas as pd, numpy as np
import plotly.express as px

def compute_agreement_matrix(opinions: pd.DataFrame) -> pd.DataFrame:
    """For each justice pair, compute agreement rate."""
    justices = set()
    for panel in opinions["panel"].dropna():
        justices.update(panel if isinstance(panel, list) else [])
    justices = sorted(justices)

    matrix = pd.DataFrame(np.nan, index=justices, columns=justices)

    for _, row in opinions.iterrows():
        panel = row.get("panel", [])
        dissenters = row.get("dissenters", [])
        if not panel:
            continue
        majority = [j for j in panel if j not in dissenters]
        for j1 in panel:
            for j2 in panel:
                if j1 == j2:
                    continue
                agree = (j1 in majority) == (j2 in majority)
                if np.isnan(matrix.loc[j1, j2]):
                    matrix.loc[j1, j2] = int(agree)
                else:
                    matrix.loc[j1, j2] = (matrix.loc[j1, j2] + int(agree)) / 2

    return matrix
```

### Feature 14 — Case Digest Email Subscription

Send weekly digest to subscribers: top opinions of the week, notable
reversals, and upcoming oral arguments.

```python
# scripts/weekly_digest.py
import smtplib, os, pandas as pd
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from utils.data_loader import load_opinions
from utils.court_calendar import fetch_oral_argument_schedule

def send_weekly_digest(recipients: list[str]) -> None:
    opinions = load_opinions()
    recent = opinions[
        pd.to_datetime(opinions["date_decided"]) >=
        pd.Timestamp.now() - pd.Timedelta(days=7)
    ].sort_values("date_decided", ascending=False)

    schedule = fetch_oral_argument_schedule()

    rows = "".join(
        f"<tr><td>{r['docket_number']}</td><td>{r['case_name'][:60]}</td>"
        f"<td>{r['disposition']}</td><td>{r['topic']}</td></tr>"
        for _, r in recent.head(10).iterrows()
    )
    upcoming = "".join(
        f"<tr><td>{r['date']}</td><td>{r['docket']}</td><td>{r['case_name'][:60]}</td></tr>"
        for _, r in schedule.head(5).iterrows()
    )
    html = f"""<html><body style="font-family:Arial;background:#f5f5f5">
    <h2>⚖️ Granite State Appeals — Weekly Digest</h2>
    <h3>Recent Decisions</h3>
    <table border="1" cellpadding="6" style="width:100%">
      <tr><th>Docket</th><th>Case</th><th>Disposition</th><th>Topic</th></tr>
      {rows}
    </table>
    <h3>Upcoming Oral Arguments</h3>
    <table border="1" cellpadding="6" style="width:100%">
      <tr><th>Date</th><th>Docket</th><th>Case</th></tr>
      {upcoming}
    </table>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "⚖️ NH Supreme Court Weekly Digest"
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], 465) as s:
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.sendmail(msg["From"], recipients, msg.as_string())
```

### Feature 15 — PDF Opinion Viewer with Highlighting

When clicking a case, display the full PDF in-browser. Highlight key
passages (holding, dissent, cited cases) based on NLP extraction.

```python
# pages/opinion_viewer.py
import streamlit as st
from pathlib import Path
import base64

def render_opinion_pdf(docket: str, pdfs_dir: Path = Path("data_files/pdfs")) -> None:
    pdf_path = pdfs_dir / f"{docket}.pdf"
    if not pdf_path.exists():
        st.info(f"PDF for {docket} not available locally.")
        # Link to NH courts website
        st.link_button("View on NH Courts Website",
                        f"https://www.courts.nh.gov/content/opinions/archive/{docket}")
        return

    with open(pdf_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="100%" height="800px" type="application/pdf"></iframe>',
        unsafe_allow_html=True,
    )
```

---

## Q4 (May–Jul 2027) — Public Tools & Infrastructure

### Feature 16 — Judge Prep Tool (Judicial Profile Deep Dives)

For attorneys appearing before specific justices, provide a deep-dive
profile: writing style, topic tendencies, questions from oral arguments,
reversal rate vs specific topics.

```python
# pages/judge_prep.py
import streamlit as st, pandas as pd

def render_judge_prep(justice_name: str, opinions: pd.DataFrame) -> None:
    st.title(f"Judge Prep: Justice {justice_name}")
    j_opinions = opinions[opinions["author"] == justice_name]
    st.subheader("By the Numbers")
    col1, col2, col3 = st.columns(3)
    col1.metric("Authored Opinions", len(j_opinions))
    col2.metric("Affirmance Rate", f"{(j_opinions['disposition']=='Affirmed').mean():.1%}")
    col3.metric("Avg Opinion Length", f"{j_opinions['case_length_chars'].mean():,.0f} chars")

    st.subheader("Topic Affirmance Rates")
    by_topic = (
        j_opinions.groupby("topic")
        .agg(cases=("docket_number", "count"),
             affirm_rate=("disposition", lambda x: (x == "Affirmed").mean()))
        .reset_index().sort_values("affirm_rate", ascending=False)
    )
    st.dataframe(by_topic, width="stretch")

    st.subheader("Writing Style")
    avg_sentence = j_opinions.get("avg_sentence_length", pd.Series()).mean()
    st.metric("Avg Sentence Length (words)", f"{avg_sentence:.1f}")
    top_phrases = _extract_top_phrases(j_opinions["opinion_text"].dropna())
    st.write("**Frequently Used Phrases:**", ", ".join(top_phrases[:10]))

def _extract_top_phrases(texts: pd.Series) -> list[str]:
    from collections import Counter
    import re
    words = Counter()
    for t in texts:
        words.update(re.findall(r'\b[A-Z][a-z]+\b', t[:2000]))
    return [w for w, _ in words.most_common(20) if len(w) > 4]
```

### Feature 17 — Caselaw Similarity Recommender

When viewing a case, surface 5 most similar cases by topic, outcome,
and semantic content. Helps attorneys find supporting precedent.

```python
# utils/case_recommender.py
import numpy as np, pandas as pd
from pathlib import Path

def get_similar_cases(
    docket: str, opinions: pd.DataFrame, top_k: int = 5
) -> pd.DataFrame:
    """Find semantically similar cases using pre-computed embeddings."""
    embeddings_file = Path("data_files/opinion_embeddings.npz")
    if not embeddings_file.exists():
        return pd.DataFrame()

    data = np.load(embeddings_file, allow_pickle=True)
    embeddings = data["embeddings"]
    docket_nums = list(data["docket_numbers"])

    if docket not in docket_nums:
        return pd.DataFrame()

    idx = docket_nums.index(docket)
    query_emb = embeddings[idx]
    scores = np.dot(embeddings, query_emb) / (
        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_emb) + 1e-8
    )
    scores[idx] = -1  # exclude self
    top_idx = np.argsort(scores)[-top_k:][::-1]
    similar_dockets = [docket_nums[i] for i in top_idx]

    return opinions[opinions["docket_number"].isin(similar_dockets)][
        ["docket_number", "case_name", "date_decided", "disposition", "topic"]
    ]
```

### Feature 18 — NH Legal Glossary & Term Definitions

Inline legal term definitions. When a legal term appears in an opinion
or UI, users can hover for a plain-English definition.

```python
# utils/legal_glossary.py
NH_LEGAL_GLOSSARY = {
    "Affirmed": "The appellate court agreed with the lower court's decision.",
    "Reversed": "The appellate court overturned the lower court's decision.",
    "Remanded": "The case was sent back to the lower court for further proceedings.",
    "Vacated": "The lower court's judgment was declared void or invalid.",
    "Per Curiam": "An opinion issued by the court as a whole without identifying the author.",
    "Writ of Certiorari": "A request for a higher court to review a lower court's decision.",
    "En Banc": "A hearing before all judges of a court, not just a panel.",
    "Habeas Corpus": "A legal action requiring that a prisoner be brought before the court.",
    "Injunction": "A court order requiring a party to do or refrain from specific actions.",
    "Mandamus": "A court order compelling a government official to perform a duty.",
    "Stare Decisis": "The principle of following precedent set by prior court decisions.",
    "Amicus Curiae": "'Friend of the court' — a party not involved in a case who offers expertise.",
    "De Novo": "A fresh review of a case without deference to the lower court's findings.",
    "Res Judicata": "A prior court judgment on the same issue prevents re-litigation.",
    "Collateral Estoppel": "Prevents re-litigation of specific issues already decided in prior cases.",
}

def get_definition(term: str) -> str | None:
    return NH_LEGAL_GLOSSARY.get(term)
```

### Feature 19 — Data Export & Open Access

Allow bulk data export (CSV/JSON) of all NH Supreme Court opinions for
researchers, journalists, and law schools.

```python
# pages/data_export.py
import streamlit as st, pandas as pd, io
from utils.data_loader import load_opinions

def render_data_export() -> None:
    st.title("📤 Data Export")
    st.caption("Download NH Supreme Court data for research purposes.")

    df = load_opinions()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("CSV Export")
        csv_data = df.drop(columns=["opinion_text"], errors="ignore").to_csv(index=False)
        st.download_button("Download Opinions CSV",
                           data=csv_data, file_name="nh_opinions.csv",
                           mime="text/csv")

    with col2:
        st.subheader("JSON Export")
        json_data = df.drop(columns=["opinion_text"], errors="ignore").to_json(
            orient="records", date_format="iso"
        )
        st.download_button("Download Opinions JSON",
                           data=json_data, file_name="nh_opinions.json",
                           mime="application/json")

    st.metric("Total Opinions Available", len(df))
    st.metric("Date Range",
              f"{df['date_decided'].min()[:4]} – {df['date_decided'].max()[:4]}")
```

### Feature 20 — Automated Data Refresh Pipeline

GitHub Action fetches new NH Supreme Court opinions weekly from the
court's official website and appends to the dataset.

```yaml
# .github/workflows/weekly_scrape.yml
name: NH Court Weekly Data Refresh
on:
  schedule:
    - cron: '0 9 * * 1'  # Monday 9 AM UTC
  workflow_dispatch:

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - name: Fetch new opinions
        run: python update_pipeline.ps1 || python scripts/fetch_new_opinions.py
      - name: Rebuild search index
        run: python scripts/rebuild_embeddings.py --incremental
      - uses: EndBug/add-and-commit@v9
        with:
          message: "Auto: weekly opinion data refresh"
```

### Feature 21 — Bar Exam Relevance Tagger

Tag opinions as particularly relevant for NH bar exam prep. Highlight
landmark cases in contracts, torts, property, criminal procedure, and evidence.

### Feature 22 — Case Timeline Visualizer

For multi-phase cases (Superior Court → Supreme Court → remand → appeal),
display a visual timeline of all proceedings, orders, and outcomes.

```python
# pages/case_timeline.py
import streamlit as st, plotly.express as px, pandas as pd

def render_case_timeline(case_history: pd.DataFrame) -> None:
    """case_history: [event_date, event_type, court, description]"""
    if case_history.empty:
        st.info("No timeline data available.")
        return
    case_history["event_date"] = pd.to_datetime(case_history["event_date"])
    fig = px.scatter(
        case_history, x="event_date", y="court",
        color="event_type", hover_name="description",
        title="Case Proceeding Timeline",
        template="plotly_dark",
    )
    fig.update_traces(marker_size=12)
    st.plotly_chart(fig, width="stretch")
```

---

## Timeline Summary

| Quarter | Focus | Key Deliverables |
|---------|-------|-----------------|
| Q1 Aug–Oct 2026 | AI search | Semantic search, outcome model, topic auto-labeler, transcript search, citation network |
| Q2 Nov 2026–Jan 2027 | Attorney/judge analytics | Attorney win rates, justice voting heatmap, outcome predictor, REST API, court calendar |
| Q3 Feb–Apr 2027 | Enhanced analytics | Readability scores, disposition trends, justice alignment, weekly digest, PDF viewer |
| Q4 May–Jul 2027 | Public tools | Judge prep tool, case recommender, legal glossary, data export, weekly pipeline, bar exam tagger, timeline visualizer |
