"""Structured Oyez metadata hydration.

Pure parsers that turn raw JSON fields stored in the case corpus into typed
``CaseEvidence`` attributes.  The prompt should never infer these structured
fields from prose when structured records exist.
"""

from __future__ import annotations

import json
from typing import Any

from .models import CaseEvidence, RetrievalHit
from .normalize import clean_text


def parse_jsonish(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, json.JSONDecodeError):
            return []
    if isinstance(value, (tuple,)):
        return [item for item in value if isinstance(item, dict)]
    return []


def summarize_decisions(value: Any) -> dict[str, Any]:
    decisions = parse_jsonish(value)
    summaries: list[dict[str, Any]] = []
    for decision in decisions:
        votes = decision.get("votes") or []
        majority: list[str] = []
        minority: list[str] = []
        authors = {
            "majority": [],
            "plurality": [],
            "dissent": [],
            "concurrence": [],
        }
        for vote in votes:
            member = vote.get("member") or {}
            name = member.get("name")
            if not name:
                continue
            side = (vote.get("vote") or "").casefold()
            opinion = (vote.get("opinion_type") or "").casefold()
            if side in {"majority", "concurrence"}:
                majority.append(name)
            elif side in {"minority", "dissent"}:
                minority.append(name)
            if "majority" == opinion:
                authors["majority"].append(name)
            elif "plurality" == opinion:
                authors["plurality"].append(name)
            elif "dissent" in opinion:
                authors["dissent"].append(name)
            elif "concurr" in opinion:
                authors["concurrence"].append(name)
        summaries.append(
            {
                "vote_split": f"{len(majority)}-{len(minority)}" if votes else "",
                "majority_justices": majority,
                "minority_justices": minority,
                "authors": authors,
                "winning_party": decision.get("winning_party"),
                "decision_type": decision.get("decision_type"),
            }
        )
    return {"decisions": summaries}


class MetadataHydrator:
    """Hydrate fused case hits into full CaseEvidence objects."""

    def __init__(self, docs_path: Any):
        import pandas as pd

        self.docs = pd.read_parquet(docs_path)
        self._by_id = {
            str(row["case_id"]): row.to_dict()
            for _, row in self.docs.iterrows()
        }

    def hydrate(self, hits: list[RetrievalHit]) -> list[CaseEvidence]:
        cases: list[CaseEvidence] = []
        for hit in hits:
            raw = self._by_id.get(str(hit.case_id)) or {}
            decisions_summary = summarize_decisions(
                raw.get("decisions_json") or raw.get("decisions")
            )
            authors = {}
            vote_split = ""
            majority_justices: list[str] = []
            minority_justices: list[str] = []
            for summary in decisions_summary.get("decisions", []):
                vote_split = vote_split or summary.get("vote_split", "")
                majority_justices = majority_justices or summary.get("majority_justices", [])
                minority_justices = minority_justices or summary.get("minority_justices", [])
                authors = authors or summary.get("authors", {})

            evidence = CaseEvidence(
                case_id=str(raw.get("case_id", hit.case_id)),
                name=clean_text(raw.get("name")) or hit.metadata.get("name", ""),
                href=clean_text(raw.get("href")) or "",
                term=clean_text(raw.get("term")),
                docket_number=clean_text(raw.get("docket_number")),
                citation=clean_text(raw.get("citation")),
                facts=clean_text(raw.get("facts")),
                question=clean_text(raw.get("question")),
                holding=clean_text(raw.get("holding")),
                description=clean_text(raw.get("description")),
                vote_split=vote_split,
                majority_justices=majority_justices,
                minority_justices=minority_justices,
                majority_authors=authors.get("majority", []) + authors.get("plurality", []),
                dissent_authors=authors.get("dissent", []),
                concurrence_authors=authors.get("concurrence", []),
                retrieval_trace=[hit],
            )
            cases.append(evidence)
        return cases