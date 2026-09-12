from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from utils.courtlistener_integration import (
    IntegrationError,
    build_indexes,
    compile_historical,
    merge_corpora,
    write_combined,
    write_historical,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _historical_root(tmp_path: Path) -> Path:
    root = tmp_path / "artifacts"
    text = root / "courtlistener" / "text" / "courtlistener_1.txt"
    text.parent.mkdir(parents=True)
    text.write_text("CourtListener source text", encoding="utf-8")
    manifest = {
        "source_document_id": "courtlistener_1",
        "case_number": "No. 99-1",
        "case_name": "Appeal of Example",
        "citation": "150 N.H. 1",
        "date_issued": "1999-01-02",
        "text_path": str(text),
        "external_ids": {"cluster_id": "1", "opinion_ids": ["10"]},
        "courtlistener_url": "https://www.courtlistener.com/opinion/1/",
    }
    manifest_path = root / "courtlistener" / "canonical_manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    _write_json(root / "courtlistener" / "runs" / "cl-gate-100" / "normalized" / "request-a.json", {
        "source_document_id": "courtlistener_1", "success": True, "validation_accepted": True,
        "summary": "short", "holdings": [], "validation": {"warnings": []},
    })
    _write_json(root / "courtlistener" / "runs" / "cl-gate-500" / "normalized" / "request-b.json", {
        "source_document_id": "courtlistener_1", "success": True, "validation_accepted": True,
        "summary": "A much richer summary", "holdings": ["Holding"], "cited_propositions": ["Rule"],
    })
    _write_json(root / "courtlistener" / "runs" / "cl-gate-500" / "normalized" / "rejected.json", {
        "source_document_id": "courtlistener_2", "success": False, "validation_accepted": False,
    })
    return root


def test_historical_compiler_preserves_manifest_and_uses_richest_candidate(tmp_path: Path) -> None:
    root = _historical_root(tmp_path)
    records, audit = compile_historical(root)

    assert records == [
        {
            "case_name": "Appeal of Example", "case_number": "No. 99-1", "citation": "150 N.H. 1",
            "cited_propositions": ["Rule"], "courtlistener_url": "https://www.courtlistener.com/opinion/1/",
            "date_issued": "1999-01-02", "external_ids": {"cluster_id": "1", "opinion_ids": ["10"]},
            "holdings": ["Holding"], "source_document_id": "courtlistener_1",
            "summary": "A much richer summary", "text_path": str(root / "courtlistener" / "text" / "courtlistener_1.txt"),
            "validation": {"accepted": True, "errors": [], "warnings": []},
        }
    ]
    assert audit["accepted_artifacts"] == 2
    assert audit["rejected_artifacts"] == 1
    assert audit["duplicate_source_ids"] == ["courtlistener_1"]
    assert not audit["missing_source_text_paths"]


def test_combined_merge_blocks_boundary_overlap_promotion(tmp_path: Path) -> None:
    root = _historical_root(tmp_path)
    write_historical(root)
    _write_json(root / "compiled" / "case_digests.json", [{
        "source_document_id": "modern_1", "case_number": "No. 99-1", "case_name": "Appeal of Example",
        "citation": "150 N.H. 1", "date_issued": "2002-01-02",
    }])
    report = write_combined(root)
    assert report["safe_to_promote"] is False
    assert (root / "compiled" / "combined_case_digests.json").exists()
    with pytest.raises(IntegrationError):
        write_combined(root, promote=True)


def test_merge_rejects_modern_records_in_historical_range() -> None:
    _, report = merge_corpora(
        [{"source_document_id": "modern_1", "date_issued": "2001-12-31"}],
        [{"source_document_id": "courtlistener_1", "date_issued": "2000-01-01"}],
    )
    assert report["modern_boundary_date_violations"] == ["modern_1"]
    assert report["safe_to_promote"] is False


def test_indexes_are_built_from_the_combined_aggregate(tmp_path: Path) -> None:
    combined = tmp_path / "combined_case_digests.json"
    _write_json(combined, [{
        "source_document_id": "courtlistener_1", "case_name": "Appeal of Example", "citation": "150 N.H. 1",
        "summary": "Historical summary", "holdings": ["Holding"], "cited_propositions": ["Rule"],
        "citation_edges": [{"target": "modern_1"}],
    }])
    result = build_indexes(combined, tmp_path / "indexes")
    assert result == {"records": 1, "citation_propositions": 1, "citation_edges": 1}
    with sqlite3.connect(tmp_path / "indexes" / "case_digests_fts.db") as connection:
        assert connection.execute("SELECT count(*) FROM case_digests_fts WHERE case_digests_fts MATCH 'Historical'").fetchone()[0] == 1
