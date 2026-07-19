from __future__ import annotations

import json
import csv
from pathlib import Path

import pandas as pd

from scripts import audit_official_pdf_manifest as audit


def test_reconciliation_csv_is_parseable():
    """A review artifact must not be able to break the Analysis page."""
    path = Path(__file__).resolve().parents[1] / "data" / "processed" / "unmatched_disposition_reconciliation.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows
    assert all(len(row) == len(rows[0]) for row in rows)
    pd.read_csv(path, dtype=str)


def test_audit_flags_missing_pdf_and_distinguishes_a_url_change(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()
    processed_dir.mkdir()

    (raw_dir / "index_2020.json").write_text(
        json.dumps([
            {"case_number": "2020-0001", "case_name": "Present", "pdf_url": "https://court/a.pdf"},
            {"case_number": "2020-0002", "case_name": "Moved", "pdf_url": "https://court/b.pdf"},
            {"case_number": "2020-0003", "case_name": "Missing", "pdf_url": "https://court/c.pdf"},
        ])
    )
    pd.DataFrame({"pdf_url": ["https://court/a.pdf", "https://old-host/b.pdf"]}).to_csv(
        processed_dir / "opinions.csv", index=False
    )

    monkeypatch.setattr(audit, "RAW_DIR", raw_dir)
    monkeypatch.setattr(audit, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(audit, "SUPPLEMENTAL_MANIFEST_PATH", tmp_path / "missing.csv")
    monkeypatch.setattr(audit, "VERIFIED_3JX_ORDERS_PATH", tmp_path / "missing-3jx.csv")

    result = audit.build_audit().set_index("listed_case_number")

    assert result.loc["2020-0001", "audit_status"] == "present"
    assert result.loc["2020-0002", "audit_status"] == "possible_url_change"
    assert result.loc["2020-0003", "audit_status"] == "missing_from_local_corpus"


def test_audit_includes_3jx_records(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()
    processed_dir.mkdir()
    (raw_dir / "3jx_2015.json").write_text(
        '[{"pdf_url": "https://courts.example/20140504.pdf", '
        '"case_number": "2014-0504", "case_name": "Gibson v. Granite"}]',
        encoding="utf-8",
    )
    pd.DataFrame({"pdf_url": ["https://courts.example/20140504.pdf"]}).to_csv(
        processed_dir / "3jx_orders.csv", index=False
    )

    monkeypatch.setattr(audit, "RAW_DIR", raw_dir)
    monkeypatch.setattr(audit, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(audit, "SUPPLEMENTAL_MANIFEST_PATH", tmp_path / "missing.csv")
    monkeypatch.setattr(audit, "VERIFIED_3JX_ORDERS_PATH", tmp_path / "missing-3jx.csv")

    result = audit.build_audit().set_index("listed_case_number")
    assert result.loc["2014-0504", "source_type"] == "3jx_order"
    assert result.loc["2014-0504", "audit_status"] == "present"
