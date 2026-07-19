"""Reciprocal-rank fusion.

Combines heterogeneous backend results into a single ranking using
weighted RRF.  Exact-name hits are weighted heavily so an unambiguous match
remains at the top of the fused list.
"""

from __future__ import annotations

from collections import defaultdict

from .models import RetrievalHit


def reciprocal_rank_fusion(
    result_sets: list[list[RetrievalHit]],
    *,
    k: int = 60,
    backend_weights: dict[str, float] | None = None,
    limit: int = 20,
) -> list[RetrievalHit]:
    weights = backend_weights or {
        "exact_name": 4.0,
        "dense_case": 2.5,
        "tfidf_case": 0.5,
        "dense_transcript": 2.0,
        "tfidf_transcript": 0.4,
    }
    totals: dict[str, float] = defaultdict(float)
    representative: dict[str, RetrievalHit] = {}
    traces: dict[str, list[dict]] = defaultdict(list)

    for hits in result_sets:
        if not hits:
            continue
        for hit in hits:
            weight = weights.get(hit.backend, 1.0)
            contribution = weight / (k + hit.rank)
            totals[hit.document_id] += contribution
            if hit.document_id not in representative:
                representative[hit.document_id] = hit
            traces[hit.document_id].append(
                {
                    "backend": hit.backend,
                    "rank": hit.rank,
                    "raw_score": hit.score,
                    "rrf": contribution,
                }
            )

    ordered = sorted(totals, key=lambda key: totals[key], reverse=True)[:limit]
    fused: list[RetrievalHit] = []
    for rank, document_id in enumerate(ordered, start=1):
        base = representative[document_id]
        fused.append(
            RetrievalHit(
                document_id=base.document_id,
                case_id=base.case_id,
                source=base.source,
                rank=rank,
                score=totals[document_id],
                backend="rrf",
                text=base.text,
                metadata={**base.metadata, "fusion_trace": traces[document_id]},
            )
        )
    return fused


def pin_unambiguous_exact(
    fused: list[RetrievalHit],
    exact_hits: list[RetrievalHit],
    *,
    threshold: float = 0.85,
) -> list[RetrievalHit]:
    """Move a single unambiguous exact match to the top of the fused list."""
    if not exact_hits:
        return fused
    top = exact_hits[0]
    if top.score < threshold:
        return fused
    target_id = top.document_id
    reordered = [hit for hit in fused if hit.document_id != target_id]
    promoted = RetrievalHit(
        document_id=top.document_id,
        case_id=top.case_id,
        source="exact",
        rank=1,
        score=float(top.score) + 1.0,
        backend="exact_name",
        text=top.text,
        metadata=top.metadata,
    )
    return [promoted] + reordered