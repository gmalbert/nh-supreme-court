"""Typed contracts for the hybrid retrieval pipeline.

The UI, provider adapters and indexing modules communicate exclusively through
these dataclasses.  Keeping the contracts frozen/typed prevents leaks of
implementation details (pandas rows, sklearn densities) into the rest of the
application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class Intent(StrEnum):
    CASE_LOOKUP = "case_lookup"
    TOPIC_OVERVIEW = "topic_overview"
    HOLDING = "holding"
    FACTS = "facts"
    VOTE_SPLIT = "vote_split"
    OPINION_AUTHOR = "opinion_author"
    JUSTICE_ALIGNMENT = "justice_alignment"
    COMPARISON = "comparison"
    TRANSCRIPT = "transcript"
    DATE_OR_PROCEDURE = "date_or_procedure"
    OTHER = "other"


@dataclass(frozen=True)
class QueryPlan:
    raw_query: str
    retrieval_query: str
    intents: tuple[Intent, ...]
    named_cases: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    dockets: tuple[str, ...] = ()
    speakers: tuple[str, ...] = ()
    requested_fields: tuple[str, ...] = ()
    requires_transcripts: bool = False
    include_prior_cases: bool = False


@dataclass(frozen=True)
class RetrievalHit:
    document_id: str
    case_id: str
    source: Literal["case", "transcript", "exact"]
    rank: int
    score: float
    backend: str
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseEvidence:
    case_id: str
    name: str
    href: str
    term: str = ""
    docket_number: str = ""
    citation: str = ""
    facts: str = ""
    question: str = ""
    holding: str = ""
    description: str = ""
    vote_split: str = ""
    majority_justices: list[str] = field(default_factory=list)
    minority_justices: list[str] = field(default_factory=list)
    majority_authors: list[str] = field(default_factory=list)
    dissent_authors: list[str] = field(default_factory=list)
    concurrence_authors: list[str] = field(default_factory=list)
    transcript_passages: list[dict[str, Any]] = field(default_factory=list)
    retrieval_trace: list[RetrievalHit] = field(default_factory=list)


@dataclass(frozen=True)
class RetrievalResponse:
    plan: QueryPlan
    cases: tuple[CaseEvidence, ...]
    sufficient: bool
    missing_fields: tuple[str, ...]
    diagnostics: dict[str, Any]