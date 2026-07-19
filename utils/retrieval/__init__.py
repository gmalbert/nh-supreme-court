"""
Durable hybrid legal retrieval package.

Public surface:

    from utils.retrieval import (
        Intent,
        QueryPlan,
        RetrievalHit,
        CaseEvidence,
        RetrievalResponse,
        RetrievalService,
        get_retrieval_service,
        evidence_to_legacy,
        build_context,
        normalize_case_name,
        clean_text,
    )

The package is intentionally import-safe: heavy backends
(``sentence-transformers``) are imported lazily inside the modules that need
them, so the rest of the retrieval chain works on a minimal stack.
"""

from __future__ import annotations

from .models import (
    CaseEvidence,
    Intent,
    QueryPlan,
    RetrievalHit,
    RetrievalResponse,
)
from .normalize import clean_text, normalize_case_name
from .service import INDEX_SCHEMA_VERSION, RetrievalService, clear_retrieval_caches, get_retrieval_service
from .legacy_adapter import evidence_to_legacy
from .context_builder import build_context

__all__ = [
    "Intent",
    "QueryPlan",
    "RetrievalHit",
    "CaseEvidence",
    "RetrievalResponse",
    "RetrievalService",
    "get_retrieval_service",
    "clear_retrieval_caches",
    "evidence_to_legacy",
    "build_context",
    "normalize_case_name",
    "clean_text",
    "INDEX_SCHEMA_VERSION",
]