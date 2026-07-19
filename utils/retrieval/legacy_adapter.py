"""Adapter converting CaseEvidence into the legacy dict format used by
``utils.chat_retriever.format_context_for_llm`` and ``utils.chat_formatter``.

Lets the chat page migrate incrementally: once the new service is wired in,
existing dict-shape code paths keep working.
"""

from __future__ import annotations

from typing import Any

from urllib.parse import quote_plus

from .models import CaseEvidence


def evidence_to_legacy(case: CaseEvidence) -> dict[str, Any]:
    """Convert a CaseEvidence into the legacy case-dict shape."""
    encoded_name = quote_plus(case.name)
    best_score = max((h.score for h in case.retrieval_trace), default=0.0)
    case_dict: dict[str, Any] = {
        "case_id": case.case_id,
        "name": case.name,
        "href": case.href,
        "source": "supreme-court",
        "score": best_score,
        "term": case.term,
        "docket_number": case.docket_number,
        "citation": case.citation,
        "facts": case.facts,
        "question": case.question,
        "holding": case.holding,
        "description": case.description,
        "vote_split": case.vote_split,
        "majority_justices": ", ".join(case.majority_justices),
        "minority_justices": ", ".join(case.minority_justices),
        "majority_opinion_authors": ", ".join(case.majority_authors),
        "dissent_authors": ", ".join(case.dissent_authors),
        "concurrence_authors": ", ".join(case.concurrence_authors),
        "snippet": case.facts or case.description or case.question,
        "url": f"/Cases?q={encoded_name}&case={encoded_name}",
    }
    opinion_authors = []
    if case.majority_authors:
        opinion_authors.append(f"majority: {', '.join(case.majority_authors)}")
    if case.dissent_authors:
        opinion_authors.append(f"dissent: {', '.join(case.dissent_authors)}")
    if case.concurrence_authors:
        opinion_authors.append(f"concurrence: {', '.join(case.concurrence_authors)}")
    if opinion_authors:
        case_dict["opinion_authors"] = "; ".join(opinion_authors)
    return case_dict