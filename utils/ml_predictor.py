"""Explainable, reproducible NH Supreme Court outcome model.

The model is intentionally descriptive rather than legal advice.  It uses only
fields available before or at decision publication and stores its training
schema beside the fitted pipeline so interactive predictions cannot silently
drift from the training encoding.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_PATH = ROOT / "data" / "processed" / "outcome_model.joblib"
AFFIRMED_OUTCOMES = {"affirmed", "affirmed_in_part"}
REVERSAL_OUTCOMES = {
    "reversed",
    "reversed_in_part",
    "vacated",
    "remanded",
    "vacated_and_remanded",
}
CATEGORICAL_FEATURES = ["topic", "appellant_type", "author", "lower_court_type"]
NUMERIC_FEATURES = [
    "year",
    "term_month",
    "word_count",
    "num_prior_cases_cited",
    "is_criminal_appeal",
    "is_administrative_appeal",
    "panel_size",
]


@dataclass(frozen=True)
class Prediction:
    probability_affirmed: float
    probability_reversed_or_vacated: float
    predicted_label: str
    confidence: float
    feature_contributions: tuple[tuple[str, float], ...]
    training_rows: int
    validation_auc: float | None


def _first_topic(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else "unknown"
    text = str(value or "").strip()
    if text.startswith("["):
        try:
            import ast

            parsed = ast.literal_eval(text)
            return str(parsed[0]) if parsed else "unknown"
        except (ValueError, SyntaxError):
            pass
    return text.strip("[]'\"").split(",")[0].strip() or "unknown"


def _panel_size(value: Any) -> int:
    if isinstance(value, dict):
        return sum(
            1
            for vote in value.values()
            if str(vote.get("vote", "")) not in {"not_participating", "recused"}
        )
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 5


def prepare_training_frame(opinions: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Normalize the app dataset to stable pre-decision predictor features."""
    frame = opinions.copy()
    outcomes = frame.get("outcome", pd.Series(index=frame.index, dtype=object))
    normalized_outcomes = outcomes.fillna("").astype(str).str.lower()
    keep = normalized_outcomes.isin(AFFIRMED_OUTCOMES | REVERSAL_OUTCOMES)
    frame = frame.loc[keep].copy()
    normalized_outcomes = normalized_outcomes.loc[keep]
    if frame.empty:
        raise ValueError("No affirmed/reversed outcomes are available for training")

    date_argued = pd.to_datetime(frame.get("date_argued"), errors="coerce")
    frame["topic"] = frame.get("topics", "unknown").map(_first_topic)
    frame["appellant_type"] = frame.get(
        "appellant_type", pd.Series("unknown", index=frame.index)
    ).fillna("unknown")
    frame["author"] = frame.get(
        "author", pd.Series("unknown", index=frame.index)
    ).fillna("unknown")
    frame["lower_court_type"] = frame.get(
        "lower_court_type", pd.Series("unknown", index=frame.index)
    ).fillna("unknown")
    frame["year"] = pd.to_numeric(frame.get("term_year"), errors="coerce").fillna(
        date_argued.dt.year
    )
    frame["term_month"] = date_argued.dt.month.fillna(1)
    frame["word_count"] = pd.to_numeric(frame.get("word_count"), errors="coerce").fillna(0)
    citations = frame.get("rsa_citations", pd.Series("[]", index=frame.index))
    frame["num_prior_cases_cited"] = citations.map(
        lambda value: len(value) if isinstance(value, list) else str(value).count(",") + int(bool(str(value).strip("[] ")))
    )
    case_type = frame.get("case_type", pd.Series("", index=frame.index)).fillna("").astype(str).str.lower()
    frame["is_criminal_appeal"] = case_type.str.contains("criminal").astype(int)
    frame["is_administrative_appeal"] = case_type.str.contains("administrative").astype(int)
    if "votes" in frame.columns:
        frame["panel_size"] = frame["votes"].map(_panel_size)
    else:
        majority = pd.to_numeric(frame.get("majority"), errors="coerce").fillna(0)
        dissent = pd.to_numeric(frame.get("dissent"), errors="coerce").fillna(0)
        frame["panel_size"] = (majority + dissent).clip(lower=1)

    X = frame[CATEGORICAL_FEATURES + NUMERIC_FEATURES].copy()
    y = normalized_outcomes.isin(AFFIRMED_OUTCOMES).astype(int)
    if y.nunique() < 2:
        raise ValueError("Outcome model requires at least two outcome classes")
    return X, y


def train_outcome_model(
    opinions: pd.DataFrame,
    model_path: str | Path | None = DEFAULT_MODEL_PATH,
) -> dict[str, Any]:
    """Fit and optionally persist a calibrated-schema logistic model."""
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    X, y = prepare_training_frame(opinions)
    preprocessor = ColumnTransformer(
        [
            (
                "category",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                CATEGORICAL_FEATURES,
            ),
            (
                "number",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median")),
                        ("scale", StandardScaler()),
                    ]
                ),
                NUMERIC_FEATURES,
            ),
        ]
    )
    pipeline = Pipeline(
        [
            ("preprocessor", preprocessor),
            ("classifier", LogisticRegression(max_iter=1500, class_weight="balanced")),
        ]
    )

    validation_auc: float | None = None
    smallest_class = int(y.value_counts().min())
    splits = min(5, smallest_class)
    if splits >= 2:
        folds = StratifiedKFold(n_splits=splits, shuffle=True, random_state=42)
        probabilities = cross_val_predict(
            pipeline, X, y, cv=folds, method="predict_proba"
        )[:, 1]
        validation_auc = float(roc_auc_score(y, probabilities))

    pipeline.fit(X, y)
    artifact = {
        "pipeline": pipeline,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "training_rows": len(X),
        "validation_auc": validation_auc,
        "label": "probability_affirmed",
        "model_version": "1.0.0",
    }
    if model_path is not None:
        import joblib

        path = Path(model_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(artifact, path)
    return artifact


def _prediction_frame(details: dict[str, Any]) -> pd.DataFrame:
    row = {feature: details.get(feature) for feature in CATEGORICAL_FEATURES + NUMERIC_FEATURES}
    row.setdefault("topic", "unknown")
    row.setdefault("appellant_type", "unknown")
    row.setdefault("author", "unknown")
    row.setdefault("lower_court_type", "unknown")
    for feature in NUMERIC_FEATURES:
        if row.get(feature) is None:
            row[feature] = 0
    return pd.DataFrame([row])


def _explain(artifact: dict[str, Any], frame: pd.DataFrame) -> tuple[tuple[str, float], ...]:
    pipeline = artifact["pipeline"]
    transformed = pipeline.named_steps["preprocessor"].transform(frame)
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    coefficients = pipeline.named_steps["classifier"].coef_[0]
    names = pipeline.named_steps["preprocessor"].get_feature_names_out()
    contributions = np.asarray(transformed)[0] * coefficients
    ranked = sorted(
        ((str(name).split("__", 1)[-1], float(value)) for name, value in zip(names, contributions)),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    return tuple(ranked[:8])


def predict_outcome(
    details: dict[str, Any],
    opinions: pd.DataFrame | None = None,
    model_path: str | Path = DEFAULT_MODEL_PATH,
) -> Prediction:
    """Predict an outcome and return local feature contributions."""
    import joblib

    path = Path(model_path)
    if path.exists():
        artifact = joblib.load(path)
    elif opinions is not None:
        artifact = train_outcome_model(opinions, model_path=None)
    else:
        raise FileNotFoundError(f"Outcome model not found: {path}")

    frame = _prediction_frame(details)
    probability = float(artifact["pipeline"].predict_proba(frame)[0, 1])
    label = "Affirmed" if probability >= 0.5 else "Reversed or vacated"
    return Prediction(
        probability_affirmed=probability,
        probability_reversed_or_vacated=1.0 - probability,
        predicted_label=label,
        confidence=max(probability, 1.0 - probability),
        feature_contributions=_explain(artifact, frame),
        training_rows=int(artifact["training_rows"]),
        validation_auc=artifact.get("validation_auc"),
    )


def prediction_as_dict(prediction: Prediction) -> dict[str, Any]:
    return asdict(prediction)
