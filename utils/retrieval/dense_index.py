"""Dense semantic case retrieval.

Designed to import ``sentence-transformers`` lazily: the rest of the retrieval
package is fully functional without it.  If the embeddings artifact is missing
or the model cannot be loaded, ``DenseCaseIndex.load`` returns ``None`` and the
service degrades to lexical-only retrieval.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .models import RetrievalHit


class DenseCaseIndex:
    def __init__(self, docs: pd.DataFrame, embeddings: np.ndarray, model_id: str):
        self.docs = docs.reset_index(drop=True)
        self.embeddings = embeddings
        if len(self.docs) != self.embeddings.shape[0]:
            raise ValueError("Case documents and embeddings are out of sync")
        self.model = None
        self.model_id = model_id

    def _ensure_model(self):
        if self.model is not None:
            return
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(self.model_id)

    @classmethod
    def load(
        cls,
        docs_path: str | os.PathLike,
        embeddings_path: str | os.PathLike,
        meta_path: str | os.PathLike,
    ) -> "DenseCaseIndex | None":
        docs_path = Path(docs_path)
        embeddings_path = Path(embeddings_path)
        meta_path = Path(meta_path)
        if not docs_path.exists() or not embeddings_path.exists() or not meta_path.exists():
            return None
        docs = pd.read_parquet(docs_path)
        embeddings = np.load(embeddings_path, mmap_mode="r")
        meta = json.loads(meta_path.read_text())
        model_id = meta.get("model") or "BAAI/bge-small-en-v1.5"
        return cls(docs, np.asarray(embeddings), model_id)

    def search(self, query: str, limit: int = 30) -> list[RetrievalHit]:
        if not query:
            return []
        self._ensure_model()
        q_text = (
            f"Represent this sentence for searching relevant passages: {query}"
        )
        encoded = self.model.encode(
            [q_text],
            normalize_embeddings=True,
        )[0].astype("float32")
        scores = self.embeddings @ encoded
        limit = min(limit, len(scores))
        indices = np.argpartition(scores, -limit)[-limit:]
        indices = indices[np.argsort(scores[indices])[::-1]]
        hits = []
        for rank, idx in enumerate(indices, start=1):
            row = self.docs.iloc[int(idx)]
            hits.append(
                RetrievalHit(
                    document_id=str(row["case_id"]),
                    case_id=str(row["case_id"]),
                    source="case",
                    rank=rank,
                    score=float(scores[idx]),
                    backend="dense_case",
                    text=str(row.get("retrieval_text", "")),
                    metadata=row.to_dict(),
                )
            )
        return hits


class DenseTranscriptIndex:
    def __init__(self, chunks: pd.DataFrame, embeddings: np.ndarray, model_id: str):
        self.chunks = chunks.reset_index(drop=True)
        self.embeddings = embeddings
        if len(self.chunks) != self.embeddings.shape[0]:
            raise ValueError("Transcript chunks and embeddings are out of sync")
        self.model_id = model_id
        self.model = None

    def _ensure_model(self):
        if self.model is not None:
            return
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(self.model_id)

    @classmethod
    def load(cls, chunks_path, embeddings_path, meta_path) -> "DenseTranscriptIndex | None":
        chunks_path = Path(chunks_path)
        embeddings_path = Path(embeddings_path)
        meta_path = Path(meta_path)
        if not chunks_path.exists() or not embeddings_path.exists() or not meta_path.exists():
            return None
        chunks = pd.read_parquet(chunks_path)
        embeddings = np.load(embeddings_path, mmap_mode="r")
        meta = json.loads(meta_path.read_text())
        return cls(chunks, np.asarray(embeddings), meta.get("model", "BAAI/bge-small-en-v1.5"))

    def search(self, query: str, limit: int = 12) -> list[RetrievalHit]:
        if not query:
            return []
        self._ensure_model()
        q_text = (
            f"Represent this sentence for searching relevant passages: {query}"
        )
        encoded = self.model.encode([q_text], normalize_embeddings=True)[0].astype("float32")
        scores = self.embeddings @ encoded
        limit = min(limit, len(scores))
        indices = np.argpartition(scores, -limit)[-limit:]
        indices = indices[np.argsort(scores[indices])[::-1]]
        hits = []
        for rank, idx in enumerate(indices, start=1):
            row = self.chunks.iloc[int(idx)]
            hits.append(
                RetrievalHit(
                    document_id=str(row.get("chunk_id", "")),
                    case_id=str(row.get("case_id", "")),
                    source="transcript",
                    rank=rank,
                    score=float(scores[idx]),
                    backend="dense_transcript",
                    text=str(row.get("text", "")),
                    metadata=row.to_dict(),
                )
            )
        return hits