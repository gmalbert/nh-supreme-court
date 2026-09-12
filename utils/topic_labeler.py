"""NH-specific legal topic labeling with optional zero-shot refinement."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable

import pandas as pd


NH_LEGAL_TOPICS = [
    "Criminal Law",
    "Family Law",
    "Contract Disputes",
    "Property Rights",
    "Administrative Law",
    "Personal Injury",
    "Constitutional Rights",
    "Workers Compensation",
    "Insurance",
    "Landlord-Tenant",
    "DUI/DWI",
    "Juvenile Justice",
    "Professional Malpractice",
    "Estate Law",
    "Zoning and Land Use",
]

TOPIC_KEYWORDS = {
    "Criminal Law": ("criminal", "defendant", "conviction", "sentence", "indictment"),
    "Family Law": ("divorce", "custody", "parenting", "marital", "child support"),
    "Contract Disputes": ("contract", "breach", "agreement", "consideration"),
    "Property Rights": ("property", "easement", "title", "boundary", "taking"),
    "Administrative Law": ("agency", "administrative", "board", "department", "rulemaking"),
    "Personal Injury": ("negligence", "injury", "damages", "tort", "duty of care"),
    "Constitutional Rights": ("constitution", "due process", "equal protection", "first amendment"),
    "Workers Compensation": ("workers' compensation", "workers compensation", "work-related injury"),
    "Insurance": ("insurance", "insurer", "coverage", "policyholder"),
    "Landlord-Tenant": ("landlord", "tenant", "lease", "eviction", "rental"),
    "DUI/DWI": ("dwi", "dui", "intoxicated", "breath test", "rsa 265-a"),
    "Juvenile Justice": ("juvenile", "delinquency", "minor child"),
    "Professional Malpractice": ("malpractice", "professional negligence", "standard of care"),
    "Estate Law": ("estate", "probate", "will", "trust", "executor"),
    "Zoning and Land Use": ("zoning", "land use", "planning board", "variance", "subdivision"),
}


@lru_cache(maxsize=1)
def _zero_shot_classifier():
    from transformers import pipeline

    return pipeline("zero-shot-classification", model="facebook/bart-large-mnli")


def _keyword_scores(text: str) -> dict[str, float]:
    lowered = (text or "").lower()
    scores: dict[str, float] = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        hits = sum(
            1
            for keyword in keywords
            if re.search(rf"\b{re.escape(keyword)}\b", lowered)
        )
        if hits:
            scores[topic] = min(0.95, 0.36 + hits * 0.13)
    return scores


def auto_label_topic(
    text: str,
    threshold: float = 0.30,
    *,
    use_zero_shot: bool = False,
) -> list[str]:
    """Return one or more NH legal topics in descending confidence order.

    Keyword labeling is deterministic and available offline.  Batch pipelines
    can opt into the roadmap's zero-shot model without making the public app
    download multi-gigabyte model artifacts on demand.
    """
    text = (text or "").strip()
    if not text:
        return []
    scores = _keyword_scores(text)
    if use_zero_shot:
        result = _zero_shot_classifier()(
            text[:2048], candidate_labels=NH_LEGAL_TOPICS, multi_label=True
        )
        for label, score in zip(result["labels"], result["scores"]):
            scores[label] = max(scores.get(label, 0.0), float(score))
    return [
        topic
        for topic, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if score >= threshold
    ]


def label_with_confidence(
    text: str,
    threshold: float = 0.30,
    *,
    use_zero_shot: bool = False,
) -> list[dict[str, float | str]]:
    scores = _keyword_scores(text)
    if use_zero_shot and text.strip():
        result = _zero_shot_classifier()(
            text[:2048], candidate_labels=NH_LEGAL_TOPICS, multi_label=True
        )
        for label, score in zip(result["labels"], result["scores"]):
            scores[label] = max(scores.get(label, 0.0), float(score))
    return [
        {"topic": topic, "confidence": score}
        for topic, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if score >= threshold
    ]


def batch_label_opinions(
    frame: pd.DataFrame,
    text_col: str = "opinion_text",
    *,
    use_zero_shot: bool = False,
) -> pd.DataFrame:
    output = frame.copy()
    output["auto_topics"] = output.get(
        text_col, pd.Series("", index=output.index)
    ).map(lambda text: auto_label_topic(str(text or ""), use_zero_shot=use_zero_shot))
    return output


def normalize_topics(values: Iterable[str]) -> list[str]:
    """Return stable, de-duplicated display labels."""
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        label = str(value).replace("_", " ").strip().title()
        if label and label not in seen:
            seen.add(label)
            normalized.append(label)
    return normalized
