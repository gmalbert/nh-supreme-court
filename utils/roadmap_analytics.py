"""Reusable analytics required by the twelve-month feature roadmap."""

from __future__ import annotations

import ast
import re
from typing import Any

import pandas as pd


PRO_APPELLANT_OUTCOMES = {"reversed", "reversed_in_part", "vacated", "remanded"}
PRO_APPELLEE_OUTCOMES = {"affirmed", "affirmed_in_part"}
BAR_SUBJECT_KEYWORDS = {
    "Contracts": ("contract", "breach", "consideration", "ucc"),
    "Torts": ("negligence", "tort", "duty", "proximate cause", "strict liability"),
    "Property": ("property", "easement", "deed", "zoning", "adverse possession"),
    "Criminal Procedure": ("search", "seizure", "miranda", "warrant", "suppression"),
    "Evidence": ("evidence", "hearsay", "privilege", "expert testimony", "authentication"),
    "Constitutional Law": ("constitution", "due process", "equal protection", "first amendment"),
    "Civil Procedure": ("jurisdiction", "summary judgment", "pleading", "service of process"),
    "Family Law": ("divorce", "custody", "parenting", "child support"),
}


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None or str(value).strip() in {"", "nan", "[]"}:
        return []
    try:
        parsed = ast.literal_eval(str(value))
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except (ValueError, SyntaxError):
        pass
    return [str(value)]


def attorney_win_rates(
    opinions: pd.DataFrame,
    counsel_facts: list[dict[str, Any]],
) -> pd.DataFrame:
    """Compute counsel win rates by side, topic, panel proxy, and year."""
    if opinions.empty or not counsel_facts:
        return pd.DataFrame()
    records = []
    opinion_index: dict[str, dict[str, Any]] = {}
    for _, opinion in opinions.iterrows():
        keys = {str(opinion.get("case_number", ""))}
        keys.update(_as_list(opinion.get("docket_numbers")))
        for key in keys:
            if key:
                opinion_index[key] = opinion.to_dict()
    for fact in counsel_facts:
        opinion = opinion_index.get(str(fact.get("docket", "")))
        if not opinion:
            continue
        outcome = str(opinion.get("outcome", "")).lower()
        side = str(fact.get("side", "")).lower()
        is_appellant = side in {"appellant", "defendant", "petitioner"}
        is_appellee = side in {"appellee", "state", "respondent"}
        won = (is_appellant and outcome in PRO_APPELLANT_OUTCOMES) or (
            is_appellee and outcome in PRO_APPELLEE_OUTCOMES
        )
        topics = _as_list(opinion.get("topics")) or ["Unknown"]
        records.append(
            {
                "attorney": fact.get("attorney_canonical") or fact.get("attorney_raw") or "Unknown",
                "docket": fact.get("docket"),
                "side": side or "unknown",
                "topic": topics[0].replace("_", " ").title(),
                "author": opinion.get("author_display") or opinion.get("author") or "Unknown",
                "year": opinion.get("term_year"),
                "outcome": outcome,
                "won": int(won),
                "confidence": fact.get("confidence", "unknown"),
            }
        )
    return pd.DataFrame(records).drop_duplicates(["attorney", "docket", "side"])


def summarize_attorney(frame: pd.DataFrame, attorney: str) -> dict[str, Any]:
    selected = frame[frame["attorney"] == attorney].copy()
    return {
        "total_cases": int(selected["docket"].nunique()) if not selected.empty else 0,
        "win_rate": float(selected["won"].mean()) if not selected.empty else 0.0,
        "unique_topics": int(selected["topic"].nunique()) if not selected.empty else 0,
        "by_topic": selected.groupby("topic")["won"].agg(["mean", "count"]).reset_index(),
        "by_author": selected.groupby("author")["won"].agg(["mean", "count"]).reset_index(),
        "over_time": selected.groupby("year")["won"].agg(["mean", "count"]).reset_index(),
    }


def justice_topic_voting(opinions_json: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for opinion in opinions_json:
        outcome = str(opinion.get("outcome", "")).lower()
        topics = _as_list(opinion.get("topics")) or ["Unknown"]
        for justice, vote in (opinion.get("votes") or {}).items():
            vote_value = str(vote.get("vote", ""))
            if vote_value in {"not_participating", "recused", "disqualified", ""}:
                continue
            for topic in topics:
                rows.append(
                    {
                        "justice": vote.get("display_name") or justice,
                        "topic": topic.replace("_", " ").title(),
                        "pro_appellant": int(outcome in PRO_APPELLANT_OUTCOMES),
                        "vote": vote_value,
                    }
                )
    return pd.DataFrame(rows)


def disposition_trends(opinions: pd.DataFrame, topic: str | None = None) -> pd.DataFrame:
    frame = opinions.copy()
    frame["year"] = pd.to_numeric(frame.get("term_year"), errors="coerce")
    frame["affirmed"] = frame.get("outcome", "").fillna("").astype(str).str.lower().isin(PRO_APPELLEE_OUTCOMES).astype(int)
    if topic:
        frame = frame[frame.get("topics", "").astype(str).str.contains(re.escape(topic), case=False, na=False)]
    return (
        frame.dropna(subset=["year"])
        .groupby("year")["affirmed"]
        .agg(["mean", "count"])
        .reset_index()
        .sort_values("year")
    )


def tag_bar_exam_relevance(text: str, topics: Any = None) -> list[dict[str, Any]]:
    corpus = f"{text or ''} {' '.join(_as_list(topics))}".lower()
    results = []
    for subject, keywords in BAR_SUBJECT_KEYWORDS.items():
        hits = [keyword for keyword in keywords if keyword in corpus]
        if hits:
            results.append(
                {
                    "subject": subject,
                    "score": min(1.0, 0.35 + 0.18 * len(hits)),
                    "matched_terms": hits,
                }
            )
    return sorted(results, key=lambda item: item["score"], reverse=True)


def build_case_timeline(
    case_number: str,
    opinions: pd.DataFrame,
    orders: pd.DataFrame | None = None,
    oral_arguments: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    opinion_rows = opinions[opinions["case_number"].astype(str) == str(case_number)]
    for _, opinion in opinion_rows.iterrows():
        if pd.notna(opinion.get("date_argued")):
            rows.append(
                {
                    "event_date": opinion.get("date_argued"),
                    "event_type": "Argument",
                    "court": "NH Supreme Court",
                    "description": "Case argued before the court",
                }
            )
        if pd.notna(opinion.get("date_issued")):
            rows.append(
                {
                    "event_date": opinion.get("date_issued"),
                    "event_type": "Opinion",
                    "court": "NH Supreme Court",
                    "description": f"Opinion issued: {opinion.get('outcome', 'disposition unavailable')}",
                }
            )
    if orders is not None and not orders.empty:
        docket_col = "docket_number" if "docket_number" in orders.columns else "case_number"
        for _, order in orders[orders[docket_col].astype(str).str.contains(str(case_number), regex=False, na=False)].iterrows():
            rows.append(
                {
                    "event_date": order.get("order_date") or order.get("date"),
                    "event_type": "Order",
                    "court": order.get("court") or "NH Supreme Court",
                    "description": order.get("description") or order.get("order_type") or "Court order",
                }
            )
    for argument in oral_arguments or []:
        if str(argument.get("case_number")) == str(case_number):
            rows.append(
                {
                    "event_date": argument.get("argument_date"),
                    "event_type": "Oral argument recording",
                    "court": "NH Supreme Court",
                    "description": argument.get("case_name") or "Oral argument",
                }
            )
    frame = pd.DataFrame(rows, columns=["event_date", "event_type", "court", "description"])
    if not frame.empty:
        frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce")
        frame = frame.dropna(subset=["event_date"]).drop_duplicates().sort_values("event_date")
    return frame
