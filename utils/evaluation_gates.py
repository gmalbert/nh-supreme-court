"""Gold-set evaluation and release promotion gates for research features."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd


DEFAULT_THRESHOLDS = {
    "citation_precision": 0.95,
    "answer_coverage": 0.70,
    "unsupported_claim_rate": 0.05,
    "temporal_leakage_rate": 0.0,
    "treatment_macro_f1": 0.80,
    "speaker_accuracy": 0.85,
    "counsel_identity_accuracy": 0.95,
}
GOLD_SET_CATEGORIES = (
    "pinpoint",
    "negative_premise",
    "conflicting_authorities",
    "no_answer_in_corpus",
    "temporal",
    "treatment",
    "holding_span",
    "speaker_attribution",
    "counsel_identity",
)


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failures: tuple[str, ...]
    metrics: dict[str, float]
    slice_failures: tuple[str, ...]


def gate_release(
    metrics: dict[str, float],
    *,
    thresholds: dict[str, float] | None = None,
    slice_metrics: pd.DataFrame | None = None,
) -> GateResult:
    required = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    failures = []
    for metric, threshold in required.items():
        if metric not in metrics:
            continue
        value = float(metrics[metric])
        if metric.endswith("_rate") and metric in {
            "unsupported_claim_rate",
            "temporal_leakage_rate",
        }:
            if value > threshold:
                failures.append(f"{metric} {value:.3f} exceeds {threshold:.3f}")
        elif value < threshold:
            failures.append(f"{metric} {value:.3f} is below {threshold:.3f}")

    slice_failures = []
    if slice_metrics is not None and not slice_metrics.empty:
        dimension_columns = [
            column
            for column in ("year", "document_quality", "case_type", "entity_frequency")
            if column in slice_metrics.columns
        ]
        for _, row in slice_metrics.iterrows():
            label = ", ".join(f"{column}={row[column]}" for column in dimension_columns)
            for metric, threshold in required.items():
                if metric not in row or pd.isna(row[metric]):
                    continue
                value = float(row[metric])
                lower_is_better = metric in {
                    "unsupported_claim_rate",
                    "temporal_leakage_rate",
                }
                failed = value > threshold if lower_is_better else value < threshold
                if failed:
                    slice_failures.append(
                        f"{label or 'slice'}: {metric}={value:.3f}"
                    )
    return GateResult(
        passed=not failures and not slice_failures,
        failures=tuple(failures),
        metrics={key: float(value) for key, value in metrics.items()},
        slice_failures=tuple(slice_failures),
    )


def validate_gold_set(cases: Iterable[dict[str, Any]]) -> list[str]:
    rows = list(cases)
    categories = {str(row.get("category")) for row in rows}
    return [
        category for category in GOLD_SET_CATEGORIES if category not in categories
    ]
