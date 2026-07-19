"""Intent-aware context construction for the prompt.

Builds bounded ``SOURCE CASE`` and ``TRANSCRIPT PASSAGE`` blocks.  Per-intent
budgets keep high-signal fields near the front of each block so the model
doesn't waste tokens scanning procedural boilerplate.
"""

from __future__ import annotations

from .models import Intent, RetrievalResponse
from .normalize import clean_text


# characters per case, per intent
BUDGETS: dict[str, int] = {
    "topic_overview": 900,
    "holding": 1500,
    "facts": 1800,
    "vote_split": 1000,
    "opinion_authors": 1000,
    "justice_alignment": 1000,
    "comparison": 1400,
    "transcript": 2500,
    "date_or_procedure": 1400,
    "case_lookup": 1600,
    "other": 1500,
}


def _truncate(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_period = truncated.rfind(". ")
    if last_period > max_chars * 0.7:
        return truncated[: last_period + 1]
    return truncated.rstrip() + "..."


def _primary_intent(intent_strs) -> str:
    if not intent_strs:
        return "other"
    for intent in intent_strs:
        if intent != Intent.TOPIC_OVERVIEW and intent != Intent.OTHER:
            return str(intent)
    return str(intent_strs[0])


def _format_case(case, budget: int) -> str:
    lines = []
    lines.append(f"Name: {case.name}")
    if case.term:
        lines.append(f"Term: {case.term}")
    if case.docket_number:
        lines.append(f"Docket: {case.docket_number}")
    if case.citation:
        lines.append(f"Citation: {case.citation}")

    field_pairs = [
        ("Facts", case.facts),
        ("Question", case.question),
        ("Holding", case.holding),
        ("Description", case.description),
    ]
    body_lines = []
    for label, value in field_pairs:
        if value:
            body_lines.append(f"{label}: {value}")
    body = "\n".join(body_lines)
    header_len = sum(len(line) + 1 for line in lines)
    body_space = max(100, budget - header_len - 200)
    lines.append(_truncate(body, body_space))

    if case.vote_split:
        lines.append(f"Vote split: {case.vote_split}")
    if case.majority_authors:
        lines.append(f"Majority author(s): {', '.join(case.majority_authors)}")
    if case.dissent_authors:
        lines.append(f"Dissent author(s): {', '.join(case.dissent_authors)}")
    if case.concurrence_authors:
        lines.append(f"Concurrence author(s): {', '.join(case.concurrence_authors)}")
    if case.majority_justices:
        lines.append(f"Majority justices: {', '.join(case.majority_justices)}")
    if case.minority_justices:
        lines.append(f"Minority justices: {', '.join(case.minority_justices)}")

    if case.href:
        lines.append(f"Source URL: {case.href}")
    return "\n".join(lines)


def _format_transcripts(case, budget: int) -> str:
    if not case.transcript_passages:
        return ""
    blocks = []
    remaining = budget
    for passage in case.transcript_passages:
        if remaining <= 60:
            break
        header = (
            "ORAL ARGUMENT TRANSCRIPT — NOT A COURT HOLDING\n"
            f"Case: {case.name}\n"
            f"Argument session: {passage.get('section_title') or passage.get('argument_title') or ''}\n"
            f"Speaker(s): {', '.join(passage.get('speakers', []))}\n"
            f"Timestamp: {passage.get('start', '')}–{passage.get('stop', '')}"
        )
        text = clean_text(passage.get("text", ""))
        block_space = max(60, remaining - len(header) - 20)
        body = _truncate(text, block_space)
        header_len = len(header)
        body_len = len(body)
        remaining -= header_len + body_len + 8
        blocks.append(f"{header}\nPassage:\n{body}")
    return "\n\n".join(blocks)


def build_context(response: RetrievalResponse) -> str:
    """Render a RetrievalResponse as bounded, intent-aware evidence blocks."""
    if not response.cases:
        return "No relevant Supreme Court cases were found in the supplied material."

    intent = _primary_intent(response.plan.intents)
    budget = BUDGETS.get(intent, BUDGETS["other"])

    sections: list[str] = []
    if response.missing_fields:
        sections.append(
            "The following requested fields are NOT available in the supplied "
            f"case records: {', '.join(response.missing_fields)}. State this "
            "limitation; do not claim the case itself was not found."
        )

    for idx, case in enumerate(response.cases, start=1):
        header = f"SOURCE CASE {idx}"
        body = _format_case(case, budget)
        sections.append(f"{header}\n{body}")
        passage_block = _format_transcripts(case, budget)
        if passage_block:
            sections.append(passage_block)
        sections.append(f"END SOURCE CASE {idx}")

    rule = (
        "Rules:\n"
        "- Use only the SOURCE CASE and TRANSCRIPT PASSAGE blocks above.\n"
        "- Cite a case only if it appears in the evidence set, formatted "
        "*Name v. Name*.\n"
        "- If a requested field is marked unavailable, say the field is "
        "unavailable; do not say the case was not found.\n"
        "- Oral-argument passages are not Court holdings. Label them as oral "
        "argument and identify the speaker.\n"
        "- Italicize case names. Do not substitute an unrelated case merely "
        "because it shares generic words."
    )
    sections.append(rule)
    return "\n\n".join(sections)