"""Stable RetrievalService facade consumed by Streamlit and tests.

The service orchestrates query analysis, exact lookup, lexical and (optional)
dense retrieval, rank fusion, metadata hydration, transcript attachment,
sufficiency evaluation, and diagnostic emission.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from .context_builder import build_context as _build_context

INDEX_SCHEMA_VERSION = "2"
from .diagnostics import LatencyRecorder, render_diagnostics
from .exact_index import ExactCaseIndex
from .fusion import pin_unambiguous_exact, reciprocal_rank_fusion
from .lexical_index import LexicalCaseIndex
from .metadata import MetadataHydrator
from .models import CaseEvidence, RetrievalHit, RetrievalResponse
from .query_analyzer import analyze_query
from .sufficiency import evaluate_sufficiency
from .transcript_index import TranscriptIndex


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA = _REPO_ROOT / "data" / "retrieval"

_service_singleton: RetrievalService | None = None


def _corpus_path(name: str) -> Path:
    return _DATA / name


def _read_columns(path: Path) -> list[str]:
    try:
        import pyarrow.parquet as pq

        schema = pq.read_schema(str(path))
        return list(schema.names)
    except Exception:
        return list(pd.read_parquet(path, columns=None).columns)


class RetrievalService:
    def __init__(
        self,
        exact: ExactCaseIndex | None,
        lexical: LexicalCaseIndex | None,
        metadata: MetadataHydrator | None,
        transcripts: TranscriptIndex | None = None,
        dense=None,
    ) -> None:
        self.exact = exact
        self.lexical = lexical
        self.metadata = metadata
        self.transcripts = transcripts
        self.dense = dense

    def is_ready(self) -> bool:
        return bool(self.exact and self.lexical and self.metadata)

    def _ensure_transcripts(self):
        if self.transcripts is not None:
            return self.transcripts
        try:
            self.transcripts = TranscriptIndex.load(
                str(_corpus_path("transcript_chunks.parquet")),
                case_docs_path=str(_corpus_path("case_documents.parquet")),
            )
        except Exception:
            self.transcripts = None
        return self.transcripts

    def retrieve(
        self,
        query: str,
        previous_cases: tuple[str, ...] = (),
        limit: int = 5,
    ) -> RetrievalResponse:
        latency = LatencyRecorder()

        latency.start("analyze")
        plan = analyze_query(query, tuple(previous_cases or ()))
        latency.stop("analyze")

        results: list[list[RetrievalHit]] = []

        latency.start("exact")
        exact_hits = self.exact.search(plan.retrieval_query, limit=10) if self.exact else []
        latency.stop("exact")
        results.append(exact_hits)

        latency.start("lexical")
        lexical_hits = (
            self.lexical.search(plan.retrieval_query, limit=30) if self.lexical else []
        )
        latency.stop("lexical")
        results.append(lexical_hits)

        latency.start("dense")
        dense_hits = []
        if self.dense is not None:
            try:
                dense_hits = self.dense.search(plan.retrieval_query, limit=60)
            except Exception:
                dense_hits = []
        latency.stop("dense")
        results.append(dense_hits)

        latency.start("fusion")
        fused = reciprocal_rank_fusion(
            results,
            limit=max(limit * 3, 15),
        )
        fused = pin_unambiguous_exact(fused, exact_hits)
        latency.stop("fusion")

        latency.start("hydrate")
        cases = self.metadata.hydrate(fused[: limit * 2]) if self.metadata else []
        latency.stop("hydrate")

        if plan.requires_transcripts:
            transcripts = self._ensure_transcripts()
            if transcripts is not None:
                passages = transcripts.search(
                    plan.retrieval_query, limit=12, speakers=list(plan.speakers) or None
                )
                cases = self._attach_transcripts(cases, passages)

        cases = self._diversify(cases, limit)
        sufficient, missing = evaluate_sufficiency(plan, cases)

        diagnostics = {
            "exact": exact_hits,
            "lexical": lexical_hits,
            "dense": dense_hits,
            "fused": fused,
            "latency": latency.as_dict(),
            "trace": render_diagnostics(
                RetrievalResponse(
                    plan=plan,
                    cases=tuple(cases),
                    sufficient=sufficient,
                    missing_fields=tuple(missing),
                    diagnostics={},
                ),
                latency.as_dict(),
            ),
        }
        return RetrievalResponse(
            plan=plan,
            cases=tuple(cases[:limit]),
            sufficient=sufficient,
            missing_fields=tuple(missing),
            diagnostics=diagnostics,
        )

    @staticmethod
    def _attach_transcripts(cases, passages):
        by_case: dict[str, list] = {}
        for p in passages:
            cid = str(p.case_id or "")
            by_case.setdefault(cid, []).append(
                {
                    "text": p.text,
                    "speakers": p.metadata.get("speakers", []),
                    "start": p.metadata.get("start"),
                    "stop": p.metadata.get("stop"),
                    "section_title": p.metadata.get("section_title"),
                    "argument_title": p.metadata.get("argument_title"),
                }
            )
        for case in cases:
            case.transcript_passages = list(by_case.get(case.case_id, []))
        return cases

    @staticmethod
    def _diversify(cases, limit):
        """Crude diversity: cap at two same-term cases for topic overviews."""
        if not cases:
            return cases
        return cases[:limit]

    def format_context(self, response: RetrievalResponse) -> str:
        return _build_context(response)


def _try_load_service() -> RetrievalService:
    """Build a RetrievalService from artifacts in data/retrieval/.

    Memoized at module scope so repeated calls in tests or non-Streamlit
    processes don't repeatedly rebuild the (heavy) TF-IDF + embedding backends.
    """
    global _service_singleton
    if _service_singleton is not None and _service_singleton.is_ready():
        return _service_singleton

    docs_path = _corpus_path("case_documents.parquet")
    if not docs_path.exists():
        return RetrievalService(None, None, None)

    cases = pd.read_parquet(docs_path)
    exact = ExactCaseIndex(cases)
    lexical = LexicalCaseIndex(cases)
    metadata = MetadataHydrator(docs_path)

    dense = None
    emb_path = _corpus_path("case_embeddings.npy")
    emb_meta_path = _corpus_path("case_embedding_meta.json")
    if emb_path.exists() and emb_meta_path.exists():
        try:
            from .dense_index import DenseCaseIndex

            dense = DenseCaseIndex.load(docs_path, emb_path, emb_meta_path)
            if dense is not None:
                dense._ensure_model()  # Eager-load model so first query is fast
        except Exception:
            dense = None

    transcripts = None  # built lazily on first transcript query

    service = RetrievalService(
        exact=exact,
        lexical=lexical,
        metadata=metadata,
        transcripts=transcripts,
        dense=dense,
    )
    if service.is_ready():
        _service_singleton = service
    return service


@st.cache_resource(show_spinner="Building hybrid retrieval indexes...")
def get_retrieval_service(
    schema_version: str = INDEX_SCHEMA_VERSION,
    corpus_mtime_ns: int | None = None,
) -> RetrievalService:
    """Return a cached RetrievalService.  Invalidated by schema or corpus mtime.

    Calling code should pass `INDEX_SCHEMA_VERSION` and the parquet mtime so a
    rebuilt corpus automatically reloads indexes.
    """
    # Reference args to prevent Streamlit from evicting the cache unexpectedly.
    _ = (schema_version, corpus_mtime_ns)
    try:
        return _try_load_service()
    except Exception as exc:  # pragma: no cover - defensive
        import streamlit as st

        st.warning(f"Retrieval service unavailable: {exc}")
        return RetrievalService(None, None, None)


def get_service_for_session() -> RetrievalService:
    """Build a service honoring artifact mtime for invalidation."""
    docs_path = _corpus_path("case_documents.parquet")
    mtime = int(docs_path.stat().st_mtime_ns) if docs_path.exists() else None
    return get_retrieval_service(INDEX_SCHEMA_VERSION, mtime)


def clear_retrieval_caches() -> None:
    """Clear Streamlit caches backing the retrieval service."""
    try:
        get_retrieval_service.clear()
    except Exception:
        pass