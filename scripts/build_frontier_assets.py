"""Build authority, provenance, evaluation, and immutable release artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.authority_graph import (
    DEFAULT_TREATMENT_MODEL_PATH,
    extract_treatments_for_opinion,
    load_treatment_classifier,
    write_treatments,
)
from utils.data_releases import create_release
from utils.evaluation_gates import validate_gold_set
from utils.ml_predictor import DEFAULT_MODEL_PATH, train_outcome_model
from utils.provenance import observation_from_record, upsert_observations


PROCESSED = ROOT / "data" / "processed"


def build_provenance(opinions: list[dict]) -> int:
    fields = (
        "date_issued",
        "outcome",
        "author",
        "topics",
        "votes",
        "summary_paragraph",
    )
    observations = [
        observation_from_record(record, field)
        for record in opinions
        for field in fields
    ]

    counsel_path = PROCESSED / "case_counsel.json"
    if counsel_path.exists():
        counsel_payload = json.loads(counsel_path.read_text(encoding="utf-8"))
        for index, fact in enumerate(counsel_payload.get("facts", [])):
            record = {
                "case_number": f"{fact.get('docket', 'unknown')}:counsel:{index}",
                "attorney_normalization": {
                    "raw": fact.get("attorney_raw"),
                    "canonical": fact.get("attorney_canonical"),
                    "role": fact.get("role"),
                    "side": fact.get("side"),
                },
                "source_url": fact.get("source_file") or "local-corpus",
                "source_sha256": fact.get("source_sha256"),
                "source_page": fact.get("source_page"),
                "confidence": fact.get("confidence"),
                "parser_version": fact.get("parser_version"),
            }
            observations.append(
                observation_from_record(
                    record,
                    "attorney_normalization",
                    method="counsel-identity-normalization",
                )
            )

    oral_path = PROCESSED / "oral_arguments.json"
    if oral_path.exists():
        oral_arguments = json.loads(oral_path.read_text(encoding="utf-8"))
        for argument in oral_arguments:
            status = str(argument.get("speaker_label_status") or "unknown")
            confidence = {
                "reviewed": 0.95,
                "diarized": 0.80,
                "heuristic": 0.35,
                "unknown": 0.20,
            }.get(status.lower(), 0.35)
            record = {
                "case_number": f"{argument.get('case_number', 'unknown')}:speaker-labels",
                "speaker_attribution": {
                    "status": status,
                    "has_speaker_labels": argument.get("has_speaker_labels", False),
                },
                "source_url": argument.get("vimeo_url") or "local-corpus",
                "confidence": confidence,
                "parser_version": (
                    f"whisper-{argument.get('model', 'unknown')}-speaker-{status}"
                ),
            }
            observations.append(
                observation_from_record(
                    record,
                    "speaker_attribution",
                    method="transcript-speaker-attribution",
                )
            )
    return upsert_observations(
        PROCESSED / "field_observations.sqlite", observations
    )


def build_authority_treatments(
    opinions: list[dict], citations: dict
) -> int:
    by_id = {
        str(opinion.get("case_number", "")): opinion for opinion in opinions
    }
    treatments = []
    classifier = load_treatment_classifier(DEFAULT_TREATMENT_MODEL_PATH)
    for case_id, citation_record in citations.items():
        opinion = by_id.get(case_id)
        text_path = PROCESSED / "text" / f"{case_id}.txt"
        if not opinion or not text_path.exists():
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace")
        treatments.extend(
            extract_treatments_for_opinion(
                opinion, citation_record, text, classifier=classifier
            )
        )
    write_treatments(
        treatments, PROCESSED / "authority_treatments.json"
    )
    return len(treatments)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-id")
    parser.add_argument("--skip-release", action="store_true")
    arguments = parser.parse_args()

    opinions_path = PROCESSED / "all_opinions.json"
    citations_path = PROCESSED / "citations.json"
    opinions = json.loads(opinions_path.read_text(encoding="utf-8"))
    citations = (
        json.loads(citations_path.read_text(encoding="utf-8"))
        if citations_path.exists()
        else {}
    )

    provenance_count = build_provenance(opinions)
    treatment_count = build_authority_treatments(opinions, citations)
    print(f"Stored {provenance_count:,} field observations")
    print(f"Stored {treatment_count:,} citation treatments")

    gold_path = ROOT / "data" / "evaluation" / "research_gold_set.json"
    gold_set = json.loads(gold_path.read_text(encoding="utf-8"))
    missing = validate_gold_set(gold_set)
    if missing:
        raise RuntimeError(
            "Gold set is missing categories: " + ", ".join(missing)
        )
    print(f"Validated {len(gold_set)} gold-set examples")

    frame = pd.read_csv(
        PROCESSED / "opinions.csv",
        parse_dates=["date_argued", "date_issued"],
        low_memory=False,
    )
    outcome_artifact = train_outcome_model(frame, DEFAULT_MODEL_PATH)
    auc = outcome_artifact.get("validation_auc")
    auc_label = f"{auc:.3f}" if auc is not None else "not available"
    print(
        f"Trained outcome model on {outcome_artifact['training_rows']:,} rows "
        f"(cross-validated AUC {auc_label})"
    )

    if not arguments.skip_release:
        missing_decision_dates = int(frame["date_issued"].isna().sum())
        release_frame = frame[frame["date_issued"].notna()].copy()
        manifest = create_release(
            release_frame,
            output_root=ROOT / "data" / "releases",
            release_id=arguments.release_id,
            known_exclusions=[
                "Machine-generated transcript text is distributed separately.",
                "Unresolved external citations are retained in review artifacts.",
                f"{missing_decision_dates} opinions lacking a decision date are "
                "excluded until they pass the release quality gate.",
            ],
            repo_root=ROOT,
        )
        print(f"Created release manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
