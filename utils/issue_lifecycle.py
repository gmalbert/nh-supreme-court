"""Doctrinal issue threads with time-relative rule states and holding diffs."""

from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode

import pandas as pd

from utils.authority_graph import Treatment


@dataclass(frozen=True)
class IssueState:
    issue_id: str
    case_id: str
    case_name: str
    decided_on: date
    rule_text: str
    disposition: str
    has_dissent: bool
    authority_status: str


@dataclass(frozen=True)
class IssueThread:
    issue_id: str
    title: str
    proposition: str
    states: tuple[IssueState, ...]
    unresolved_split: bool

    @property
    def first_appearance(self) -> IssueState | None:
        return self.states[0] if self.states else None

    @property
    def latest_state(self) -> IssueState | None:
        return self.states[-1] if self.states else None


def issue_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")[:72] or "issue"


def _topics(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = ast.literal_eval(str(value))
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except (ValueError, SyntaxError):
        return [str(value)] if value else []


def _authority_status(
    case_id: str, treatments: list[Treatment], as_of: date
) -> str:
    relevant = [
        treatment
        for treatment in treatments
        if treatment.cited_case == case_id and treatment.decided_on <= as_of
    ]
    if not relevant:
        return "No classified later treatment"
    latest = max(relevant, key=lambda treatment: treatment.decided_on)
    return latest.display_label


def build_issue_threads(
    opinions: pd.DataFrame,
    treatments: list[Treatment] | None = None,
    *,
    as_of: date | None = None,
    min_cases: int = 2,
) -> list[IssueThread]:
    """Build stable topic-level threads from dated opinion propositions."""
    research_date = as_of or date.today()
    treatment_rows = treatments or []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for _, row in opinions.iterrows():
        decided = pd.to_datetime(row.get("date_issued"), errors="coerce")
        if pd.isna(decided) or decided.date() > research_date:
            continue
        record = row.to_dict()
        for topic in _topics(row.get("topics")):
            title = topic.replace("_", " ").title()
            grouped.setdefault(title, []).append(record)

    threads = []
    for title, rows in grouped.items():
        if len(rows) < min_cases:
            continue
        states = []
        for row in sorted(rows, key=lambda item: str(item.get("date_issued", ""))):
            decided_on = pd.to_datetime(row.get("date_issued")).date()
            case_id = str(row.get("case_number", ""))
            rule = str(row.get("summary_paragraph") or "").strip()
            if not rule:
                rule = f"{row.get('case_name', case_id)} — published disposition: {row.get('outcome', 'unknown')}."
            states.append(
                IssueState(
                    issue_id=issue_slug(title),
                    case_id=case_id,
                    case_name=str(row.get("case_name") or case_id),
                    decided_on=decided_on,
                    rule_text=rule,
                    disposition=str(row.get("outcome") or "unknown"),
                    has_dissent=bool(row.get("has_dissent", False)),
                    authority_status=_authority_status(
                        case_id, treatment_rows, research_date
                    ),
                )
            )
        outcomes = {state.disposition for state in states}
        has_divided_state = any(state.has_dissent for state in states)
        unresolved = has_divided_state and len(outcomes) > 1
        threads.append(
            IssueThread(
                issue_id=issue_slug(title),
                title=title,
                proposition=f"How the NH Supreme Court has treated {title.lower()} issues.",
                states=tuple(states),
                unresolved_split=unresolved,
            )
        )
    return sorted(threads, key=lambda thread: (-len(thread.states), thread.title))


def thread_as_of(thread: IssueThread, as_of: date) -> IssueThread:
    states = tuple(state for state in thread.states if state.decided_on <= as_of)
    outcomes = {state.disposition for state in states}
    return IssueThread(
        issue_id=thread.issue_id,
        title=thread.title,
        proposition=thread.proposition,
        states=states,
        unresolved_split=any(state.has_dissent for state in states)
        and len(outcomes) > 1,
    )


def holding_diff(earlier: str, later: str) -> str:
    """Return a compact word-level diff marking additions and removals."""
    diff = difflib.ndiff((earlier or "").split(), (later or "").split())
    parts = []
    for token in diff:
        if token.startswith("+ "):
            parts.append(f"**+{token[2:]}**")
        elif token.startswith("- "):
            parts.append(f"~~{token[2:]}~~")
        elif token.startswith("  "):
            parts.append(token[2:])
    return " ".join(parts)


def stable_issue_url(
    issue_id: str, as_of: date, base_path: str = "/legal-intelligence"
) -> str:
    return f"{base_path}?{urlencode({'issue': issue_id, 'as_of': as_of.isoformat()})}"


def proposition_cards(thread: IssueThread) -> dict[str, IssueState | None]:
    majority = next(
        (state for state in reversed(thread.states) if not state.has_dissent),
        thread.latest_state,
    )
    divided = next(
        (state for state in reversed(thread.states) if state.has_dissent), None
    )
    return {"majority": majority, "divided": divided}
