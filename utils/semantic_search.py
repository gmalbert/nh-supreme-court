"""Semantic opinion search with a dense-index-first, offline-safe fallback.

The application already ships a hybrid retrieval corpus.  This module gives
the roadmap feature a small public API and keeps model downloads out of the
interactive Streamlit request path.  Dense artifacts can be built explicitly;
when they are unavailable, the existing TF-IDF index remains fully usable.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EMBEDDINGS_FILE = ROOT / "data" / "retrieval" / "opinion_embeddings.npz"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _value(record: Any, *names: str) -> str:
    for name in names:
        if hasattr(record, "get"):
            value = record.get(name, "")
        else:
            value = getattr(record, name, "")
        if value is not None and str(value).strip() not in {"", "nan", "None"}:
            if isinstance(value, (list, tuple, set)):
                return " ".join(str(item) for item in value)
            return str(value)
    return ""


def _embedding_text(record: Any) -> str:
    return " | ".join(
        part
        for part in (
            _value(record, "case_number", "docket_number"),
            _value(record, "case_name", "name"),
            _value(record, "topics", "topic"),
            _value(record, "summary_paragraph", "summary", "description"),
        )
        if part
    )


@lru_cache(maxsize=2)
def _model(model_name: str = DEFAULT_MODEL):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def build_opinion_embeddings(
    opinions,
    output_file: str | Path = DEFAULT_EMBEDDINGS_FILE,
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 32,
) -> Path:
    """Build normalized sentence-transformer embeddings for opinion records."""
    output = Path(output_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    records = [row for _, row in opinions.iterrows()]
    texts = [_embedding_text(row) for row in records]
    docket_numbers = [
        _value(row, "case_number", "docket_number") for row in records
    ]
    embeddings = _model(model_name).encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    np.savez_compressed(
        output,
        embeddings=np.asarray(embeddings, dtype="float32"),
        docket_numbers=np.asarray(docket_numbers, dtype=object),
    )
    output.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "model": model_name,
                "rows": len(docket_numbers),
                "dimensions": int(embeddings.shape[1]) if len(embeddings) else 0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return output


def semantic_search(
    query: str,
    top_k: int = 10,
    embeddings_file: str | Path = DEFAULT_EMBEDDINGS_FILE,
) -> list[dict[str, Any]]:
    """Return the most relevant opinions for a natural-language query.

    Dense artifacts are used when present.  The fallback deliberately calls
    the maintained offline search service rather than failing or downloading a
    model during a public request.
    """
    query = (query or "").strip()
    if not query:
        return []

    path = Path(embeddings_file)
    if path.exists():
        data = np.load(path, allow_pickle=True)
        embeddings = np.asarray(data["embeddings"], dtype="float32")
        dockets = data["docket_numbers"]
        meta_path = path.with_suffix(".meta.json")
        model_name = DEFAULT_MODEL
        if meta_path.exists():
            model_name = json.loads(meta_path.read_text(encoding="utf-8")).get(
                "model", DEFAULT_MODEL
            )
        query_vector = _model(model_name).encode(
            [query], normalize_embeddings=True
        )[0]
        scores = embeddings @ np.asarray(query_vector, dtype="float32")
        indices = np.argsort(scores)[::-1][: max(1, top_k)]
        return [
            {
                "docket_number": str(dockets[index]),
                "score": float(scores[index]),
                "backend": "dense",
            }
            for index in indices
        ]

    from utils.text_search import search as lexical_semantic_search

    results = lexical_semantic_search(query, top_k=top_k)
    normalized = []
    for result in results:
        row = dict(result)
        docket = row.get("docket_number")
        if isinstance(docket, str) and docket.startswith("["):
            try:
                import ast

                parsed = ast.literal_eval(docket)
                docket = parsed[0] if parsed else ""
            except (ValueError, SyntaxError):
                docket = ""
        row["docket_number"] = docket or row.get("href", "")
        row["backend"] = "tfidf-fallback"
        normalized.append(row)
    return normalized


def embeddings_available(
    embeddings_file: str | Path = DEFAULT_EMBEDDINGS_FILE,
) -> bool:
    return Path(embeddings_file).exists()
