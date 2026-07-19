"""Deterministic query analysis.

Identifies requested fields and explicit entities (citations, dockets,
speakers).  Does NOT rewrite legal topics into landmark-case lists — those are
the job of the retrieval backends, not the analyzer.
"""

from __future__ import annotations

import re

from .models import Intent, QueryPlan


FIELD_PATTERNS: dict[str, tuple[Intent, str]] = {
    "holding": (Intent.HOLDING, r"\b(?:hold|holding|rule|decide[ds]?|decision(?!\s+split))\b"),
    "facts": (Intent.FACTS, r"\b(?:facts?|happened|background|what happened)\b"),
    "vote_split": (Intent.VOTE_SPLIT, r"\b(?:vote|split|unanimous|decision split|[0-9]+-[0-9]+)\b"),
    "opinion_authors": (
        Intent.OPINION_AUTHOR,
        r"\b(?:who wrote|author(?:ed)?|wrote the (?:majority |dissenting )?opinion|"
        r"majority opinion|dissent(?:ing)? opinion|concurrence)\b",
    ),
    "justice_alignment": (
        Intent.JUSTICE_ALIGNMENT,
        r"\b(?:which justices|who joined|majority justices|dissenters?|"
        r"who dissented|who was in the majority)\b",
    ),
    "transcript_passages": (
        Intent.TRANSCRIPT,
        r"\b(?:oral argument|transcript transcription|oral argument transcript|"
        r"asked during argument|questioned during oral argument|exchange during argument|"
        r"argue during oral argument|what did .* justice .* ask|what did .* say during oral argument)\b",
    ),
    "date_or_procedure": (
        Intent.DATE_OR_PROCEDURE,
        r"\b(?:argued|decided|date|procedural|lower court|docket|when did)\b",
    ),
}

CITATION_RE = re.compile(r"\b\d+\s+U\.S\.\s+\d+\b", re.I)
DOCKET_RE = re.compile(r"\b(?:No\.\s*)?\d{1,2}-\d{2,5}\b", re.I)

_COMPARISON_RE = re.compile(
    r"\b(?:compare|difference|differ|differences|versus|vs\.|changed|overruled|"
    r"over time|line of cases)\b"
)
_REFERENTIAL_RE = re.compile(
    r"\b(?:that case|those cases|the dissent|the majority|the opinion|"
    r"they|these decisions|those decisions|later cases?)\b"
)

_PARTY_HINT_RE = re.compile(r"\b([A-Z][A-Za-z'\-]+)\s+v\.?\s+([A-Z][A-Za-z'\-]+)")
_SINGLE_PARTY_RE = re.compile(r"\b([A-Z][A-Za-z'\-]{3,})\b")


def _named_cases(query: str) -> tuple[str, ...]:
    """Extract explicit full case names from a query string."""
    candidates: list[str] = []
    for match in _PARTY_HINT_RE.finditer(query):
        left = match.group(1)
        right = match.group(2)
        if left and right:
            candidates.append(f"{left} v. {right}")
    return tuple(dict.fromkeys(candidates))


def analyze_query(
    query: str,
    previous_cases: tuple[str, ...] = (),
) -> QueryPlan:
    """Return a deterministic QueryPlan for a natural-language question.

    The analyzer never nukes the user's natural language: ``retrieval_query``
    is the original query (with referential context appended), preserving the
    user's vocabulary for downstream backends.
    """
    if not query:
        query = ""
    lowered = query.casefold()

    intents: list[Intent] = []
    requested: list[str] = []
    for field, (intent, pattern) in FIELD_PATTERNS.items():
        if re.search(pattern, lowered):
            if intent not in intents:
                intents.append(intent)
            if field not in requested:
                requested.append(field)

    if _PARTY_HINT_RE.search(query) or _SINGLE_PARTY_RE.search(query):
        if Intent.CASE_LOOKUP not in intents:
            intents.append(Intent.CASE_LOOKUP)

    if not intents:
        intents.append(Intent.TOPIC_OVERVIEW)

    comparative = bool(_COMPARISON_RE.search(lowered))
    if comparative and Intent.COMPARISON not in intents:
        intents.append(Intent.COMPARISON)

    referential = bool(_REFERENTIAL_RE.search(lowered))
    include_prior = referential and bool(previous_cases)

    if referential and include_prior and Intent.TOPIC_OVERVIEW not in intents:
        intents.append(Intent.TOPIC_OVERVIEW)

    citations = tuple(CITATION_RE.findall(query))
    dockets = tuple(DOCKET_RE.findall(query))
    named = _named_cases(query)

    retrieval_query = query
    if include_prior and previous_cases:
        retrieval_query = f"{query}\nPrior cases: {', '.join(previous_cases)}"

    return QueryPlan(
        raw_query=query,
        retrieval_query=retrieval_query,
        intents=tuple(intents),
        named_cases=named,
        citations=citations,
        dockets=dockets,
        speakers=(),
        requested_fields=tuple(requested),
        requires_transcripts=Intent.TRANSCRIPT in intents,
        include_prior_cases=include_prior,
    )