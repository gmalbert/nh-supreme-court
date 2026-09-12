"""Time-aware citation-treatment extraction with evidence spans."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


EXTRACTOR_VERSION = "treatment-rules-v1.0.0"
DEFAULT_TREATMENT_MODEL_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "processed"
    / "treatment_classifier.joblib"
)
CLASS_THRESHOLDS = {
    "followed": 0.82,
    "distinguished": 0.88,
    "limited": 0.90,
    "questioned": 0.90,
    "overruled": 0.95,
}
RULES = (
    ("overruled", 0.99, re.compile(r"\b(?:overrule[ds]?|overruled by|no longer good law)\b", re.I)),
    ("distinguished", 0.97, re.compile(r"\b(?:distinguish(?:ed|es|ing)?|factually distinct)\b", re.I)),
    ("limited", 0.94, re.compile(r"\b(?:limit(?:ed|s|ing)?|narrow(?:ed|s|ing)?|confine[ds]?)\b", re.I)),
    ("questioned", 0.93, re.compile(r"\b(?:question(?:ed|s|ing)?|decline to follow|doubt(?:ed|s)?|criticiz(?:ed|es|ing))\b", re.I)),
    (
        "followed",
        0.90,
        re.compile(
            r"\b(?:(?:we|this court|the court)\s+(?:have\s+)?"
            r"(?:follow(?:ed)?|adhere(?:d)? to|rely(?:ing|ied)? on)|"
            r"consistent with|controlled by)\b",
            re.I,
        ),
    ),
)


@dataclass(frozen=True)
class Treatment:
    citing_case: str
    cited_case: str
    label: str
    confidence: float
    evidence_start: int
    evidence_end: int
    evidence_text: str
    decided_on: date
    extractor_version: str = EXTRACTOR_VERSION

    @property
    def display_label(self) -> str:
        threshold = CLASS_THRESHOLDS.get(self.label, 1.0)
        return self.label if self.confidence >= threshold else "treatment unclear"


def classify_treatment(
    window: str, classifier: Any | None = None
) -> tuple[str, float]:
    """Apply high-precision rules, then an optional reviewed-example model."""
    for label, confidence, pattern in RULES:
        if pattern.search(window or ""):
            return label, confidence
    if classifier is not None and str(window or "").strip():
        pipeline = (
            classifier.get("pipeline")
            if isinstance(classifier, dict)
            else classifier
        )
        probabilities = pipeline.predict_proba([window])[0]
        best_index = max(range(len(probabilities)), key=probabilities.__getitem__)
        label = str(pipeline.classes_[best_index])
        return label, float(probabilities[best_index])
    return "unclear", 0.45


def train_treatment_classifier(
    reviewed_examples: Iterable[dict[str, Any]],
    model_path: str | Path | None = None,
) -> dict[str, Any]:
    """Train a legal-text classifier only from explicitly reviewed examples."""
    rows = [
        {
            "text": str(
                example.get("evidence_text")
                or example.get("text")
                or example.get("window")
                or ""
            ).strip(),
            "label": str(example.get("label") or "").strip().lower(),
        }
        for example in reviewed_examples
        if bool(example.get("reviewed", True))
    ]
    rows = [
        row
        for row in rows
        if row["text"] and row["label"] in CLASS_THRESHOLDS
    ]
    labels = {row["label"] for row in rows}
    if len(rows) < 4 or len(labels) < 2:
        raise ValueError(
            "Treatment classifier requires at least four reviewed examples "
            "spanning two labels"
        )

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    pipeline = Pipeline(
        [
            (
                "vectorizer",
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=1,
                    sublinear_tf=True,
                ),
            ),
            (
                "classifier",
                LogisticRegression(
                    max_iter=1500,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )
    pipeline.fit(
        [row["text"] for row in rows],
        [row["label"] for row in rows],
    )
    artifact = {
        "pipeline": pipeline,
        "training_rows": len(rows),
        "labels": sorted(labels),
        "model_version": "treatment-tfidf-logreg-v1.0.0",
        "training_source": "reviewed_examples_only",
    }
    if model_path is not None:
        import joblib

        output = Path(model_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(artifact, output)
    return artifact


def load_treatment_classifier(path: str | Path) -> dict[str, Any] | None:
    model_path = Path(path)
    if not model_path.exists():
        return None
    import joblib

    return joblib.load(model_path)


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def extract_treatments_for_opinion(
    opinion: dict[str, Any],
    citation_record: dict[str, Any],
    opinion_text: str,
    *,
    window_radius: int = 280,
    classifier: Any | None = None,
) -> list[Treatment]:
    """Classify resolved and unresolved citations while preserving evidence."""
    decided_on = _date(opinion.get("date_issued"))
    if decided_on is None:
        return []
    citations = [
        *(citation_record.get("cites") or []),
        *(citation_record.get("unresolved") or []),
    ]
    treatments = []
    for citation in citations:
        start = int(citation.get("start_pos") or 0)
        end = int(citation.get("end_pos") or start)
        evidence_start = max(0, start - window_radius)
        evidence_end = min(len(opinion_text), end + window_radius)
        evidence = opinion_text[evidence_start:evidence_end].strip()
        label, confidence = classify_treatment(evidence, classifier)
        cited_case = str(
            citation.get("resolved_case_number")
            or citation.get("text")
            or citation.get("citation")
            or "unknown authority"
        )
        treatments.append(
            Treatment(
                citing_case=str(opinion.get("case_number", "")),
                cited_case=cited_case,
                label=label,
                confidence=confidence,
                evidence_start=evidence_start,
                evidence_end=evidence_end,
                evidence_text=evidence,
                decided_on=decided_on,
            )
        )
    return treatments


def controlling_treatments(
    edges: Iterable[Treatment], case_id: str, as_of: date
) -> list[Treatment]:
    """Return treatments that existed on the research date, newest first."""
    return sorted(
        (
            edge
            for edge in edges
            if edge.cited_case == case_id and edge.decided_on <= as_of
        ),
        key=lambda edge: edge.decided_on,
        reverse=True,
    )


def treatment_to_dict(treatment: Treatment) -> dict[str, Any]:
    payload = asdict(treatment)
    payload["decided_on"] = treatment.decided_on.isoformat()
    payload["display_label"] = treatment.display_label
    return payload


def write_treatments(treatments: Iterable[Treatment], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([treatment_to_dict(item) for item in treatments], indent=2),
        encoding="utf-8",
    )
    return output


def load_treatments(path: str | Path) -> list[Treatment]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    rows = json.loads(file_path.read_text(encoding="utf-8"))
    return [
        Treatment(
            citing_case=row["citing_case"],
            cited_case=row["cited_case"],
            label=row["label"],
            confidence=float(row["confidence"]),
            evidence_start=int(row["evidence_start"]),
            evidence_end=int(row["evidence_end"]),
            evidence_text=row.get("evidence_text", ""),
            decided_on=date.fromisoformat(row["decided_on"]),
            extractor_version=row.get("extractor_version", EXTRACTOR_VERSION),
        )
        for row in rows
    ]
