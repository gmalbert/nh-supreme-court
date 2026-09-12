"""Claim-level evidence verification for generated legal-research answers."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable


MIN_ENTAILMENT_SCORE = 0.82
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]*")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class VerifiedClaim:
    claim: str
    case_id: str
    source_span: str
    start_char: int
    end_char: int
    entailment_score: float


@dataclass(frozen=True)
class VerificationResult:
    publishable_text: str
    verified_claims: tuple[VerifiedClaim, ...]
    unsupported_claims: tuple[str, ...]
    answer_coverage: float
    unsupported_claim_rate: float


def publishable(claim: VerifiedClaim) -> bool:
    return (
        claim.entailment_score >= MIN_ENTAILMENT_SCORE
        and len(claim.source_span.split()) >= 6
    )


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_RE.findall(text or "")
        if len(token) > 2
    }


def _source_text(source: dict[str, Any]) -> str:
    fields = (
        "source_span",
        "snippet",
        "facts_of_the_case",
        "conclusion",
        "summary",
        "description",
        "retrieval_text",
        "text",
    )
    return "\n".join(
        str(source.get(field, "")) for field in fields if source.get(field)
    )


def _case_id(source: dict[str, Any]) -> str:
    return str(
        source.get("case_id")
        or source.get("docket_number")
        or source.get("case_number")
        or source.get("href")
        or source.get("name")
        or "unknown"
    )


def _candidate_spans(text: str, claim: str) -> Iterable[tuple[str, int, int]]:
    claim_words = max(6, len(claim.split()))
    sentences = [part.strip() for part in SENTENCE_RE.split(text) if part.strip()]
    cursor = 0
    for index, sentence in enumerate(sentences):
        start = text.find(sentence, cursor)
        if start < 0:
            start = text.find(sentence)
        end = start + len(sentence)
        cursor = max(cursor, end)
        yield sentence, max(0, start), max(0, end)
        if index + 1 < len(sentences) and len(sentence.split()) < claim_words:
            combined = f"{sentence} {sentences[index + 1]}"
            yield combined, max(0, start), max(0, start + len(combined))


def _score(claim: str, span: str) -> float:
    claim_tokens = _tokens(claim)
    span_tokens = _tokens(span)
    if not claim_tokens or not span_tokens:
        return 0.0
    overlap = len(claim_tokens & span_tokens)
    precision = overlap / len(claim_tokens)
    recall = overlap / min(len(span_tokens), max(len(claim_tokens) * 2, 1))
    token_score = 2 * precision * recall / max(precision + recall, 1e-9)
    sequence_score = SequenceMatcher(None, claim.lower(), span.lower()).ratio()
    exact_bonus = 0.12 if claim.lower() in span.lower() else 0.0
    return min(1.0, 0.72 * token_score + 0.28 * sequence_score + exact_bonus)


def verify_claim(claim: str, sources: Iterable[dict[str, Any]]) -> VerifiedClaim:
    best = VerifiedClaim(claim, "", "", 0, 0, 0.0)
    for source in sources:
        text = _source_text(source)
        for span, start, end in _candidate_spans(text, claim):
            score = _score(claim, span)
            if score > best.entailment_score:
                best = VerifiedClaim(
                    claim=claim,
                    case_id=_case_id(source),
                    source_span=span,
                    start_char=start,
                    end_char=end,
                    entailment_score=round(score, 4),
                )
    return best


def decompose_claims(answer: str) -> list[str]:
    """Split prose into checkable sentences while dropping non-claims."""
    claims = []
    for sentence in SENTENCE_RE.split(answer or ""):
        cleaned = re.sub(r"^[-*#\d.)\s]+", "", sentence).strip()
        if len(cleaned.split()) < 5:
            continue
        if cleaned.endswith(":"):
            continue
        claims.append(cleaned)
    return claims


def verify_answer(answer: str, sources: Iterable[dict[str, Any]]) -> VerificationResult:
    source_list = list(sources)
    claims = decompose_claims(answer)
    checked = [verify_claim(claim, source_list) for claim in claims]
    verified = tuple(claim for claim in checked if publishable(claim))
    unsupported = tuple(claim.claim for claim in checked if not publishable(claim))
    if verified:
        published = "\n\n".join(claim.claim for claim in verified)
    else:
        published = (
            "I could not verify a publishable answer against the retrieved source spans. "
            "Review the source records below or refine the question."
        )
    total = len(checked)
    coverage = len(verified) / total if total else 0.0
    unsupported_rate = len(unsupported) / total if total else 0.0
    return VerificationResult(
        publishable_text=published,
        verified_claims=verified,
        unsupported_claims=unsupported,
        answer_coverage=coverage,
        unsupported_claim_rate=unsupported_rate,
    )


def evaluation_metrics(results: Iterable[VerificationResult]) -> dict[str, float]:
    rows = list(results)
    if not rows:
        return {"answer_coverage": 0.0, "unsupported_claim_rate": 0.0}
    return {
        "answer_coverage": sum(row.answer_coverage for row in rows) / len(rows),
        "unsupported_claim_rate": sum(row.unsupported_claim_rate for row in rows) / len(rows),
    }


def verified_claim_to_dict(claim: VerifiedClaim) -> dict[str, Any]:
    return asdict(claim)
