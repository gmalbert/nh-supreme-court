"""
Vote block parsing utilities for NH Supreme Court opinions.
"""

from __future__ import annotations

import re
from typing import Dict, Optional

from utils.constants import (
    JUSTICE_LAST_NAME_MAP,
    VOTE_MAJORITY,
    VOTE_DISSENT,
    VOTE_CONCUR_SEPARATE,
    VOTE_NOT_PARTICIPATING,
    VOTE_RECUSED,
    VOTE_DISQUALIFIED,
    JUSTICE_DISPLAY,
    JUSTICE_KEYS,
)

# ── Regex patterns ─────────────────────────────────────────────────────────────
_NAME_FRAG = r"[A-Z][A-Z\-]+"
_COMPOUND_NAME = rf"(?:{_NAME_FRAG}(?:\s+{_NAME_FRAG})?)"

AUTHOR_RE = re.compile(
    r"^(PER CURIAM|([A-Z\-]+(?:\s+[A-Z\-]+)?),\s+(C\.J\.|J\.))[.\s]",
    re.MULTILINE,
)

# Disposition keyword patterns (within a line segment)
_CONCURRED_RE = re.compile(r"\bconcurred\b", re.IGNORECASE)
_DISSENTED_RE = re.compile(r"\bdissented\b", re.IGNORECASE)
_CONCUR_SPECIAL_RE = re.compile(r"\bconcurred\s+specially\b", re.IGNORECASE)
_NOT_PARTICIPATING_RE = re.compile(
    r"\b(?:did not participate|not participat|recused|disqualified)\b",
    re.IGNORECASE,
)


def _names_in_clause(clause: str) -> list[str]:
    """Return all justice keys mentioned by last name in the clause."""
    upper = clause.upper()
    keys = []
    for name, key in JUSTICE_LAST_NAME_MAP.items():
        if name in upper and key not in keys:
            keys.append(key)
    return keys


def parse_vote_block(text: str, author_key: str = "per_curiam") -> Dict[str, dict]:
    """
    Parse the vote block from an NH Supreme Court opinion.
    Returns a dict mapping justice_key → vote record dict.

    Strategy: scan all lines of the opinion.  For each line
    (or two-line pair for wrapped text), detect the disposition keyword and
    assign votes to any justice named in that segment.  The vote block in
    NH SC opinions appears right after the outcome word (Affirmed/Reversed),
    which may be well before the end when a dissent opinion follows.
    """
    votes: Dict[str, str] = {}
    notes: Dict[str, str] = {}

    lines = text.split("\n")

    # Build segments: individual lines + adjacent-line pairs to handle wrapping
    segments = list(lines)
    for i in range(len(lines) - 1):
        segments.append(lines[i] + " " + lines[i + 1])

    def _apply_clause(clause: str) -> None:
        """Classify a single semicolon-separated clause and assign votes."""
        if _NOT_PARTICIPATING_RE.search(clause):
            vote_type = VOTE_NOT_PARTICIPATING
        elif _CONCUR_SPECIAL_RE.search(clause):
            vote_type = VOTE_CONCUR_SEPARATE
        elif _DISSENTED_RE.search(clause):
            vote_type = VOTE_DISSENT
        elif _CONCURRED_RE.search(clause):
            vote_type = VOTE_MAJORITY
        else:
            return  # no disposition keyword

        for key in _names_in_clause(clause):
            existing = votes.get(key)
            if existing is None:
                votes[key] = vote_type
                notes[key] = clause.strip()
            elif (vote_type == VOTE_NOT_PARTICIPATING
                  and existing not in (VOTE_MAJORITY, VOTE_DISSENT, VOTE_CONCUR_SEPARATE)):
                votes[key] = vote_type
                notes[key] = clause.strip()
            # else: active vote already assigned — first wins; skip

    for segment in segments:
        # Split on semicolons so each clause (concurred / dissented) is classified
        # independently — avoids misclassifying "X concurred; Y dissented" as all dissent.
        for clause in re.split(r";", segment):
            _apply_clause(clause)

    # The author is implicitly in the majority
    if author_key and author_key != "per_curiam" and author_key not in votes:
        votes[author_key] = VOTE_MAJORITY

    result = {}
    for jkey in JUSTICE_KEYS:
        display = JUSTICE_DISPLAY.get(jkey, jkey)
        role = "chief_justice" if "C.J." in display else "associate_justice"
        vote = votes.get(jkey, VOTE_NOT_PARTICIPATING)
        note_text = notes.get(jkey, None)
        result[jkey] = {
            "display_name": display,
            "role": role,
            "vote": vote,
            "note": note_text,
        }

    return result


def vote_summary(votes: Dict[str, dict]) -> dict:
    """Return aggregate vote counts."""
    counts = {
        "majority": 0,
        "dissent": 0,
        "concur_separate": 0,
        "not_participating": 0,
    }
    for v in votes.values():
        vtype = v.get("vote", "not_participating")
        if vtype in (VOTE_MAJORITY,):
            counts["majority"] += 1
        elif vtype == VOTE_DISSENT:
            counts["dissent"] += 1
        elif vtype == VOTE_CONCUR_SEPARATE:
            counts["concur_separate"] += 1
        else:
            counts["not_participating"] += 1

    participating = counts["majority"] + counts["dissent"] + counts["concur_separate"]
    vote_str = f"{counts['majority']}-{counts['dissent']}" if participating else "N/A"
    return {
        **counts,
        "vote_string": vote_str,
        "is_unanimous": counts["dissent"] == 0 and participating > 0,
        "has_dissent": counts["dissent"] > 0,
        "has_separate_concurrence": counts["concur_separate"] > 0,
    }
