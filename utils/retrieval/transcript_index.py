"""Transcript retrieval orchestration.

Combines lexical and (optional) dense transcript indexes, applies speaker
filters from the query plan, and maps retrieved passages back to cases by
``case_id`` using an argument->case lookup derived from the Oyez
``oral_argument_audio`` field in the case corpus.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from .lexical_index import LexicalTranscriptIndex
from .models import RetrievalHit
from .normalize import clean_text


class TranscriptIndex:
    """Finds oral-argument transcript passages for a query.

    This class is constructed lazily by the RetrievalService when transcripts
    artifacts exist.  Dense retrieval is optional; when unavailable the index
    falls back to lexical TF-IDF.
    """

    def __init__(
        self,
        chunks: pd.DataFrame,
        lexical: LexicalTranscriptIndex,
        dense=None,
        case_map: dict[int, str] | None = None,
    ) -> None:
        self.chunks = chunks.reset_index(drop=True)
        self.lexical = lexical
        self.dense = dense
        self.case_map = case_map or {}

    @classmethod
    def load(
        cls,
        chunks_path: str,
        dense_chunks_path: str | None = None,
        dense_embeddings_path: str | None = None,
        dense_meta_path: str | None = None,
        case_docs_path: str | None = None,
    ) -> "TranscriptIndex | None":
        from pathlib import Path

        chunks_path = Path(chunks_path)
        if not chunks_path.exists():
            return None
        chunks = pd.read_parquet(chunks_path)
        lexical = LexicalTranscriptIndex(chunks, text_column="text")
        dense = None
        if dense_chunks_path and dense_embeddings_path and dense_meta_path:
            from .dense_index import DenseTranscriptIndex

            dense = DenseTranscriptIndex.load(
                dense_chunks_path, dense_embeddings_path, dense_meta_path
            )

        case_map: dict[int, str] = {}
        if case_docs_path:
            case_docs_path = Path(case_docs_path)
            if case_docs_path.exists():
                df = pd.read_parquet(case_docs_path, columns=["case_id", "oral_argument_audio"])
                for _, row in df.iterrows():
                    audio = row.get("oral_argument_audio")
                    if not audio:
                        continue
                    try:
                        records = json.loads(audio) if isinstance(audio, str) else audio
                    except (TypeError, json.JSONDecodeError):
                        records = []
                    if not isinstance(records, list):
                        continue
                    for rec in records:
                        if isinstance(rec, dict) and rec.get("id"):
                            case_map[int(rec["id"])] = str(row["case_id"])
        return cls(chunks, lexical, dense=dense, case_map=case_map)

    def search(
        self,
        query: str,
        limit: int = 12,
        speakers: list[str] | None = None,
    ) -> list[RetrievalHit]:
        if not query:
            return []
        hits = self.lexical.search(query, limit=limit * 3, speakers=speakers)
        if self.dense is not None:
            dense_hits = self.dense.search(query, limit=limit * 3)
            hits = self._merge(hits, dense_hits)
        # Attach case_id using case_map by argument_id
        enriched: list[RetrievalHit] = []
        seen_chunk_ids: set[str] = set()
        for hit in hits:
            chunk_id = hit.document_id
            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            meta = dict(hit.metadata)
            arg_id = meta.get("argument_id")
            case_id = self.case_map.get(int(arg_id)) if arg_id else None
            if not case_id:
                case_id = hit.case_id
            meta["case_id"] = case_id or ""
            enriched.append(
                RetrievalHit(
                    document_id=chunk_id,
                    case_id=str(case_id or ""),
                    source="transcript",
                    rank=hit.rank,
                    score=hit.score,
                    backend=hit.backend,
                    text=hit.text,
                    metadata=meta,
                )
            )
        return enriched[:limit]

    @staticmethod
    def _merge(*result_sets: list[RetrievalHit]) -> list[RetrievalHit]:
        scored: dict[str, tuple[float, RetrievalHit]] = {}
        for hits in result_sets:
            for hit in hits:
                cur = scored.get(hit.document_id)
                if cur is None or hit.score > cur[0]:
                    scored[hit.document_id] = (hit.score, hit)
        ordered = sorted(scored.values(), key=lambda x: x[0], reverse=True)
        return [hit for _, hit in ordered]