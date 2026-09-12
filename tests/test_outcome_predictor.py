from __future__ import annotations

import pandas as pd

from utils.ml_predictor import predict_outcome, prepare_training_frame, train_outcome_model


def _training_data() -> pd.DataFrame:
    rows = []
    outcomes = ["affirmed", "reversed"] * 12
    for index, outcome in enumerate(outcomes):
        rows.append(
            {
                "case_number": f"2024-{index:04d}",
                "outcome": outcome,
                "topics": ["criminal" if index % 3 else "civil"],
                "appellant_type": "individual" if index % 2 else "government",
                "author": "justice_a" if index % 2 else "justice_b",
                "lower_court_type": "superior",
                "term_year": 2024,
                "date_argued": f"2024-{(index % 12) + 1:02d}-01",
                "word_count": 2500 + index * 100,
                "rsa_citations": ["RSA 1:1"],
                "case_type": "criminal" if index % 3 else "civil",
                "majority": 5,
                "dissent": 0,
            }
        )
    return pd.DataFrame(rows)


def test_model_preparation_and_explainable_prediction():
    opinions = _training_data()
    X, y = prepare_training_frame(opinions)
    assert len(X) == len(opinions)
    assert set(y.unique()) == {0, 1}
    artifact = train_outcome_model(opinions, model_path=None)
    assert artifact["training_rows"] == len(opinions)
    prediction = predict_outcome(
        {
            "topic": "criminal",
            "appellant_type": "individual",
            "author": "unknown",
            "lower_court_type": "superior",
            "year": 2026,
            "term_month": 4,
            "word_count": 4000,
            "num_prior_cases_cited": 3,
            "is_criminal_appeal": 1,
            "is_administrative_appeal": 0,
            "panel_size": 5,
        },
        opinions=opinions,
        model_path="missing-for-test.joblib",
    )
    assert 0 <= prediction.probability_affirmed <= 1
    assert prediction.feature_contributions
