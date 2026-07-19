"""Evidence sufficiency evaluation.

A refusal should be precise: distinguish "case not found" from
"case found but requested field missing" from "below confidence threshold".
"""

from __future__ import annotations

from typing import Iterable

from .models import CaseEvidence, QueryPlan


REQUIRED_BY_FIELD = {
    "holding": lambda c: bool(c.holding),
    "facts": lambda c: bool(c.facts),
    "vote_split": lambda c: bool(c.vote_split),
    "opinion_authors": lambda c: bool(
        c.majority_authors or c.dissent_authors or c.concurrence_authors
    ),
    "justice_alignment": lambda c: bool(c.majority_justices or c.minority_justices),
    "transcript_passages": lambda c: bool(c.transcript_passages),
}


def evaluate_sufficiency(
    plan: QueryPlan,
    cases: Iterable[CaseEvidence],
) -> tuple[bool, list[str]]:
    cases = list(cases)
    if not cases:
        return False, ["relevant_case"]

    missing: list[str] = []
    for field in plan.requested_fields:
        if field == "facts" and not any(bool(c.facts) for c in cases):
            # facts are frequently missing from Oyez, but case description may
            # still provide them.  Do not treat a missing facts field alone as
            # a hard failure when description has substance.
            if any(bool(c.description) for c in cases):
                continue
            missing.append(field)
            continue
        predicate = REQUIRED_BY_FIELD.get(field)
        if predicate and not any(predicate(c) for c in cases):
            missing.append(field)
    return not missing, missing