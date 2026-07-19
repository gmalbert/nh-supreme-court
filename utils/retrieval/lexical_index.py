"""Lexical (TF-IDF) case-text index.

Wraps the legacy ``utils.text_search`` behavior in a backend that returns
``RetrievalHit`` objects.  BM25 could be substituted later behind the same
interface; a light TF-IDF adapter is enough to keep the application portable.
"""

from __future__ import annotations

import re
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .models import RetrievalHit
from .normalize import clean_text


_LEXICAL_STOPWORDS = {
    "what", "who", "when", "where", "which", "was", "did", "does", "do",
    "the", "is", "are", "in", "of", "and", "or", "a", "an", "with", "for",
    "case", "court", "decision", "opinion", "holding", "rule", "split",
    "vote", "justice", "judge", "supreme", "issue", "held", "say", "rights",
    "right", "law", "legal", "question", "fact", "facts",
}


def _distinctive_query_tokens(query: str) -> set[str]:
    lowered = (query or "").lower()
    base = {
        token
        for token in re.findall(r"[a-z][a-z0-9]+", lowered)
        if len(token) >= 5 and token not in _LEXICAL_STOPWORDS
    }
    # Include singular/plural variants so "schools" matches "School" in case
    # names without requiring a separate stemmer dependency.
    variants: set[str] = set()
    for token in base:
        variants.add(token)
        if token.endswith("s"):
            variants.add(token[:-1])
        else:
            variants.add(token + "s")
    return variants


class LexicalCaseIndex:
    def __init__(self, cases: pd.DataFrame, text_column: str = "retrieval_text"):
        self.docs = cases.reset_index(drop=True)
        self.text_column = text_column
        texts = [
            (clean_text(row.get(text_column)) or clean_text(row.get("name")))
            for _, row in self.docs.iterrows()
        ]
        texts = [t if t else " " for t in texts]
        self.vectorizer = TfidfVectorizer(
            max_features=30_000,
            ngram_range=(1, 2),
            min_df=2,
            sublinear_tf=True,
            stop_words="english",
        )
        self.matrix = self.vectorizer.fit_transform(texts)
        self.texts = texts
        self._name_tokens = [
            set(re.findall(r"[a-z0-9]+", str(name).lower()))
            for name in self.docs["name"].fillna("")
        ]

    def search(self, query: str, limit: int = 25) -> list[RetrievalHit]:
        if not query or not query.strip():
            return []
        q_vec = self.vectorizer.transform([query.lower()])
        scores = cosine_similarity(q_vec, self.matrix).ravel()
        # Title-token boost: distinctive query tokens that appear in a case
        # name provide a small, vocabulary-free signal that helps short
        # proper-noun queries (e.g. "Pickering") without resorting to
        # curated landmark-case lists.
        distinctive = _distinctive_query_tokens(query)
        if distinctive:
            for i, name_tokens in enumerate(self._name_tokens):
                overlap = distinctive & name_tokens
                if overlap:
                    scores[i] += 0.25 * len(overlap)
        limit = min(limit, len(scores))
        indices = np.argsort(scores)[::-1][:limit]
        hits: list[RetrievalHit] = []
        rank = 0
        for idx in indices:
            score = float(scores[idx])
            if score <= 0:
                continue
            rank += 1
            row = self.docs.iloc[idx]
            hits.append(
                RetrievalHit(
                    document_id=str(row["case_id"]),
                    case_id=str(row["case_id"]),
                    source="case",
                    rank=rank,
                    score=score,
                    backend="tfidf_case",
                    text=self.texts[idx],
                    metadata=row.to_dict(),
                )
            )
        return hits


class LexicalTranscriptIndex:
    """Lexical index over transcript chunks with case-aware filters."""

    def __init__(self, chunks: pd.DataFrame, text_column: str = "text"):
        self.chunks = chunks.reset_index(drop=True)
        self.text_column = text_column
        # Lazy case-id mapping
        texts = [str("") if clean_text(row.get(text_column)) is None else clean_text(row.get(text_column)) for _, row in self.chunks.iterrows()]
        texts = [t if t else " " for t in texts]
        self.vectorizer = TfidfVectorizer(
            max_features=30_000,
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
            stop_words="english",
        )
        self.matrix = self.vectorizer.fit_transform(texts)
        self.texts = texts

    def search(
        self,
        query: str,
        limit: int = 12,
        speakers: Iterable[str] | None = None,
    ) -> list[RetrievalHit]:
        if not query or not query.strip():
            return []
        q_vec = self.vectorizer.transform([query.lower()])
        scores = cosine_similarity(q_vec, self.matrix).ravel()
        indices = np.argsort(scores)[::-1]
        hits: list[RetrievalHit] = []
        rank = 0
        for idx in indices:
            if rank >= limit:
                break
            score = float(scores[idx])
            if score <= 0:
                continue
            row = self.chunks.iloc[idx]
            if speakers:
                speaker_set = {s.casefold() for s in speakers}
                row_speakers = {str(s).casefold() for s in (row.get("speakers") or [])}
                if not row_speakers & speaker_set:
                    continue
            rank += 1
            hits.append(
                RetrievalHit(
                    document_id=str(row.get("chunk_id", "")),
                    case_id=str(row.get("case_id", "")),
                    source="transcript",
                    rank=rank,
                    score=score,
                    backend="tfidf_transcript",
                    text=self.texts[idx],
                    metadata=row.to_dict(),
                )
            )
        return hits