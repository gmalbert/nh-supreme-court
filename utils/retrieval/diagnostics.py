"""Diagnostics: trace logging, JSON records, and debug rendering for Streamlit.

Privacy: never log raw user queries by default.  Use a hash unless an explicit
privacy-enabled debug flag is set.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from .models import RetrievalHit, RetrievalResponse


def query_hash(query: str) -> str:
    if not query:
        return ""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


def serialize_hits(hits: list[RetrievalHit]) -> list[dict[str, Any]]:
    return [
        {
            "document_id": h.document_id,
            "backend": h.backend,
            "rank": h.rank,
            "raw_score": round(float(h.score), 6),
            "name": (h.metadata or {}).get("name", ""),
        }
        for h in hits
    ]


class LatencyRecorder:
    def __init__(self) -> None:
        self._starts: dict[str, float] = {}
        self._totals: dict[str, int] = {}

    def start(self, label: str) -> None:
        self._starts[label] = time.perf_counter()

    def stop(self, label: str) -> None:
        start = self._starts.pop(label, None)
        if start is None:
            return
        elapsed = int((time.perf_counter() - start) * 1000)
        self._totals[label] = elapsed

    def as_dict(self) -> dict[str, int]:
        return dict(self._totals)


def render_diagnostics(response: RetrievalResponse, latency: dict[str, int]) -> dict[str, Any]:
    return {
        "query_hash": query_hash(response.plan.raw_query),
        "intent": [str(intent) for intent in response.plan.intents],
        "requested_fields": list(response.plan.requested_fields),
        "missing_fields": list(response.missing_fields),
        "sufficient": response.sufficient,
        "latency_ms": latency,
        "top_cases": [
            {
                "name": case.name,
                "rrf": round(float(case.retrieval_trace[0].score), 6) if case.retrieval_trace else 0,
                "backends": [t.backend for t in case.retrieval_trace],
            }
            for case in response.cases
        ],
        "exact": serialize_hits(response.diagnostics.get("exact", [])),
        "lexical": serialize_hits(response.diagnostics.get("lexical", [])),
        "dense": serialize_hits(response.diagnostics.get("dense", [])),
        "fused": serialize_hits(response.diagnostics.get("fused", [])),
    }


def render_diagnostics_json(response: RetrievalResponse, latency: dict[str, int]) -> str:
    return json.dumps(render_diagnostics(response, latency), indent=2)