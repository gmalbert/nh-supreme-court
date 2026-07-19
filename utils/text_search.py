"""
TF-IDF semantic case search for NH Supreme Court.

Builds a TF-IDF index from the retrieval corpus parquet.
Fully offline — no API key or internet required.
"""

from __future__ import annotations
import os
import re
import pandas as pd
import numpy as np
import streamlit as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CORPUS_PARQUET = os.path.join(_REPO_ROOT, "data", "retrieval", "case_documents.parquet")


# Case summaries—especially older ones—often use period-specific language
# rather than the modern umbrella term a user searches for. Keep these
# expansions deliberately narrow so the retrieved records remain the sole
# source of legal claims made by the chat model.
_TOPIC_EXPANSIONS = (
    (
        ("lgbtq", "lgbt", "queer"),
        "gay lesbian bisexual transgender homosexual same-sex marriage "
        "sexual orientation gender identity",
    ),
)


def expand_query(query: str) -> str:
    """Add corpus vocabulary for recognized legal-topic umbrella terms."""
    text = (query or "").strip()
    lowered = text.lower()
    additions = [
        expansion
        for triggers, expansion in _TOPIC_EXPANSIONS
        if any(trigger in lowered for trigger in triggers)
    ]
    if (
        any(term in lowered for term in ("speech", "expression", "first amendment"))
        and any(term in lowered for term in ("school", "student", "campus"))
    ):
        additions.append(
            "Tinker Bethel Hazelwood Morse Mahanoy student speech First Amendment "
            "school-sponsored off-campus expression armband newspaper censorship"
        )
    return " ".join([text, *additions]).strip()


_NAME_QUERY_STOPWORDS = {
    "case", "court", "decision", "education", "free", "holding", "justice",
    "opinion", "school", "schools", "split", "supreme", "vote", "what",
    "when", "where", "which", "with",
}


def _name_query_tokens(query: str) -> set[str]:
    """Return distinctive words that may identify a case by party name."""
    lowered = (query or "").lower()
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", lowered)
        if len(token) >= 4 and token not in _NAME_QUERY_STOPWORDS
    }
    if (
        any(term in lowered for term in ("speech", "expression", "first amendment"))
        and any(term in lowered for term in ("school", "student", "campus"))
    ):
        tokens.update({"tinker", "bethel", "hazelwood", "morse", "mahanoy"})
    return tokens


@st.cache_resource(show_spinner="Building search index...")
def get_index() -> tuple:
    """
    Build and cache the TF-IDF vectorizer, matrix, and index dataframe.
    Using @st.cache_resource to ensure this expensive operation runs only once.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    # Load NH retrieval corpus
    if not os.path.exists(_CORPUS_PARQUET):
        # Return empty index if corpus not built yet
        return None, None, pd.DataFrame()

    df = pd.read_parquet(
        _CORPUS_PARQUET,
        columns=["name", "term", "href", "docket_number", "facts", "question", "description", "retrieval_text"],
    )

    # Use the pre-built retrieval_text field
    df["_text"] = df["retrieval_text"].fillna("").str.lower()
    df = df[df["_text"].str.len() > 20].reset_index(drop=True)

    vec = TfidfVectorizer(
        max_features=30_000,
        ngram_range=(1, 2),
        min_df=2,
        sublinear_tf=True,
        stop_words="english",
    )
    matrix = vec.fit_transform(df["_text"])
    index_df = df[["name", "term", "href", "docket_number"]].copy()

    return vec, matrix, index_df


def search(query: str, top_k: int = 10) -> list[dict]:
    """Return up to top_k cases whose text best matches the query string.

    Each result dict has: name, term, href, docket_number, score.
    """
    vectorizer, tfidf_matrix, index_df = get_index()

    if not query or not query.strip():
        return []

    from sklearn.metrics.pairwise import cosine_similarity

    q_vec = vectorizer.transform([expand_query(query).lower()])
    scores = cosine_similarity(q_vec, tfidf_matrix).flatten()

    # A party name explicitly supplied by the user is stronger evidence than
    # generic legal words such as "justice" or "decision." TF-IDF alone can
    # otherwise bury Pickering beneath cases with "Department of Justice" in
    # their titles. Apply a deterministic title boost before selecting top-k.
    query_name_tokens = _name_query_tokens(query)
    if query_name_tokens:
        for i, name in enumerate(index_df["name"].fillna("")):
            name_tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
            overlap = query_name_tokens & name_tokens
            if overlap:
                scores[i] += 0.75 * len(overlap)
    top_idx = scores.argsort()[::-1][:top_k]

    results = []
    for i in top_idx:
        score = float(scores[i])
        if score < 0.01:
            break
        row = index_df.iloc[i]
        results.append({
            "name": row["name"],
            "term": row["term"],
            "href": row["href"],
            "docket_number": row.get("docket_number", ""),
            "score": round(score, 4),
        })
    return results


def is_available() -> bool:
    """Return True if the retrieval corpus exists and sklearn is importable."""
    if not os.path.exists(_CORPUS_PARQUET):
        return False
    try:
        import sklearn  # noqa: F401
        return True
    except ImportError:
        return False
