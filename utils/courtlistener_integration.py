"""Deterministic provenance-preserving CourtListener corpus integration.

This module deliberately has no dependency on the application's legacy dataset
builder.  It operates on the artifact layout documented in
``COURTLISTENER_HISTORICAL_INTEGRATION.md`` so source corpora can remain
separate until a reviewed merge is explicitly promoted.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


HISTORICAL_START_YEAR = 1980
HISTORICAL_END_YEAR = 2001


class IntegrationError(ValueError):
    """Raised when an aggregate cannot safely be produced or promoted."""


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    """Atomically write stable JSON so reruns do not create noisy changes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _rows_from_json(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    for key in ("records", "cases", "case_digests", "items"):
        if isinstance(payload, dict) and isinstance(payload.get(key), list):
            return [row for row in payload[key] if isinstance(row, dict)]
    raise IntegrationError(f"{path} does not contain a JSON record list")


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise IntegrationError(f"Invalid JSONL at {path}:{number}") from exc
                if isinstance(value, dict):
                    rows.append(value)
    return rows


def _source_id(row: dict[str, Any]) -> str:
    value = row.get("source_document_id") or row.get("document_id")
    return str(value).strip() if value is not None else ""


def _run_request_id(path: Path, artifacts_root: Path) -> tuple[str, str]:
    relative = path.relative_to(artifacts_root)
    parts = relative.parts
    run_id = parts[2] if len(parts) > 2 and parts[0:2] == ("courtlistener", "runs") else ""
    return run_id, path.stem


def _richness(row: dict[str, Any]) -> tuple[int, int]:
    """Prefer populated output, not merely a later run or larger raw file."""
    ignored = {"success", "validation_accepted", "validation", "request_id", "run_id"}
    fields = [value for key, value in row.items() if key not in ignored and value not in (None, "", [], {})]
    return len(fields), sum(len(json.dumps(value, ensure_ascii=False, sort_keys=True)) for value in fields)


def _manifest_map(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise IntegrationError(f"Canonical manifest is missing: {path}")
    rows = _jsonl_rows(path) if path.suffix == ".jsonl" else _rows_from_json(path)
    mapped: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for row in rows:
        identifier = _source_id(row)
        if not identifier:
            continue
        if identifier in mapped and mapped[identifier] != row:
            duplicates.append(identifier)
        else:
            mapped[identifier] = row
    if duplicates:
        raise IntegrationError(f"Manifest has conflicting source_document_id values: {sorted(set(duplicates))[:5]}")
    return mapped


def _merged_record(extraction: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep source metadata authoritative while retaining every extraction field."""
    record = dict(extraction)
    # The extraction pipeline stores legal-analysis fields beneath ``extraction``.
    # Flatten those fields to match jp.compile's public digest schema while keeping
    # the source artifact's operational provenance on the record as well.
    nested_extraction = record.pop("extraction", None)
    if isinstance(nested_extraction, dict):
        record.update(nested_extraction)
    record.update({key: value for key, value in metadata.items() if value not in (None, "", [], {})})
    record["source_document_id"] = _source_id(metadata) or _source_id(extraction)
    validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
    record["validation"] = {
        **validation,
        "accepted": True,
        "errors": record.pop("validation_errors", validation.get("errors", [])) or [],
        "warnings": record.pop("validation_warnings", validation.get("warnings", [])) or [],
    }
    record.pop("success", None)
    record.pop("validation_accepted", None)
    return record


def compile_historical(artifacts_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compile every accepted CourtListener extraction run into one aggregate."""
    artifacts_root = Path(artifacts_root)
    source_root = artifacts_root / "courtlistener"
    manifest = _manifest_map(source_root / "canonical_manifest.jsonl")
    candidates: dict[str, list[tuple[tuple[int, int], str, str, dict[str, Any]]]] = defaultdict(list)
    rejected = 0
    missing_ids = 0
    for path in sorted(source_root.glob("runs/*/normalized/*.json")):
        row = _read_json(path)
        if not isinstance(row, dict):
            rejected += 1
            continue
        if row.get("success") is not True or row.get("validation_accepted") is not True:
            rejected += 1
            continue
        identifier = _source_id(row)
        if not identifier:
            missing_ids += 1
            continue
        run_id, request_id = _run_request_id(path, artifacts_root)
        candidates[identifier].append((_richness(row), run_id, request_id, row))

    records: list[dict[str, Any]] = []
    discarded: list[dict[str, str]] = []
    missing_manifest: list[str] = []
    missing_text_paths: list[str] = []
    for identifier in sorted(candidates):
        # Highest richness wins; run and request ID make an equal-quality choice stable.
        ordered = sorted(candidates[identifier], key=lambda item: (-item[0][0], -item[0][1], item[1], item[2]))
        chosen = ordered[0]
        if identifier not in manifest:
            missing_manifest.append(identifier)
            continue
        record = _merged_record(chosen[3], manifest[identifier])
        text_path = str(record.get("text_path") or "")
        if text_path and not Path(text_path).exists():
            missing_text_paths.append(text_path)
        records.append(record)
        for item in ordered[1:]:
            discarded.append({"source_document_id": identifier, "chosen_run_id": chosen[1], "discarded_run_id": item[1], "discarded_request_id": item[2]})

    records.sort(key=_record_sort_key)
    audit = {
        "compiler": "courtlistener_historical",
        "input_artifacts": sum(len(items) for items in candidates.values()) + rejected + missing_ids,
        "accepted_artifacts": sum(len(items) for items in candidates.values()),
        "rejected_artifacts": rejected,
        "artifacts_without_source_document_id": missing_ids,
        "canonical_records": len(records),
        "duplicate_source_ids": sorted(identifier for identifier, items in candidates.items() if len(items) > 1),
        "discarded_candidates": discarded,
        "missing_manifest_joins": missing_manifest,
        "missing_source_text_paths": sorted(missing_text_paths),
    }
    return records, audit


def write_historical(artifacts_root: Path) -> dict[str, Any]:
    root = Path(artifacts_root)
    records, audit = compile_historical(root)
    _write_json(root / "courtlistener" / "compiled" / "case_digests.json", {
        "record_count": len(records), "records": records,
    })
    _write_json(root / "courtlistener" / "compiled" / "audit.json", audit)
    return audit


def _normalized_citation(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _date_year(value: Any) -> int | None:
    match = re.match(r"^(\d{4})-\d{2}-\d{2}$", str(value or ""))
    return int(match.group(1)) if match else None


def _record_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return str(row.get("date_issued") or ""), str(row.get("citation") or ""), _source_id(row)


def _canonicalize(
    rows: Iterable[dict[str, Any]], source_name: str, *, resolve_with_quality_precedence: bool = False
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Canonicalize source IDs, optionally applying a declared quality rule.

    The quality rule is intentionally narrow: it is for duplicate extraction
    runs of the *same source document* within one source corpus.  It chooses
    the richest accepted output, then a stable run/request tie breaker; it
    never merges records merely because their captions or citations match.
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        identifier = _source_id(row)
        if not identifier:
            raise IntegrationError(f"{source_name} contains a row without source_document_id")
        grouped[identifier].append(row)
    result: dict[str, dict[str, Any]] = {}
    resolutions: list[dict[str, Any]] = []
    for identifier, candidates in grouped.items():
        unique = {json.dumps(candidate, ensure_ascii=False, sort_keys=True): candidate for candidate in candidates}
        if len(unique) == 1:
            result[identifier] = next(iter(unique.values()))
            continue
        if not resolve_with_quality_precedence:
            raise IntegrationError(f"{source_name} contains conflicting duplicate ID {identifier}")
        ordered = sorted(
            candidates,
            key=lambda row: (-_richness(row)[0], -_richness(row)[1], str(row.get("run_id") or ""), str(row.get("request_id") or "")),
        )
        chosen = ordered[0]
        result[identifier] = chosen
        resolutions.append({
            "source_document_id": identifier,
            "rule": "richest_accepted_output_then_run_id_then_request_id",
            "chosen_run_id": chosen.get("run_id"),
            "discarded_run_ids": [item.get("run_id") for item in ordered[1:]],
        })
    return result, resolutions


def enrich_with_manifest(
    rows: list[dict[str, Any]], manifest_path: Path | None, date_overrides_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Attach source-manifest fields without allowing them to erase a digest value."""
    manifest = _manifest_map(manifest_path) if manifest_path else {}
    overrides = _read_json(date_overrides_path) if date_overrides_path and date_overrides_path.exists() else {}
    if not isinstance(overrides, dict):
        raise IntegrationError(f"Date overrides must be an object: {date_overrides_path}")
    enriched: list[dict[str, Any]] = []
    for row in rows:
        identifier = _source_id(row)
        merged = {**manifest.get(identifier, {}), **row}
        override = overrides.get(identifier)
        if isinstance(override, dict) and override.get("date_issued"):
            merged["date_issued"] = override["date_issued"]
            merged["date_override"] = override
        enriched.append(merged)
    return enriched


def merge_corpora(modern_rows: list[dict[str, Any]], historical_rows: list[dict[str, Any]], reviewed_overlaps: set[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge source-separated aggregates, reporting rather than collapsing overlaps."""
    reviewed_overlaps = reviewed_overlaps or set()
    modern, modern_resolutions = _canonicalize(modern_rows, "modern aggregate", resolve_with_quality_precedence=True)
    historical, historical_resolutions = _canonicalize(historical_rows, "historical aggregate")
    ids_in_both = sorted(set(modern) & set(historical))
    collisions = [identifier for identifier in ids_in_both if modern[identifier] != historical[identifier]]
    if collisions:
        raise IntegrationError(f"Conflicting cross-source IDs: {collisions[:5]}")
    combined = {**modern, **historical}
    historical_bad_dates = sorted(identifier for identifier, row in historical.items() if (year := _date_year(row.get("date_issued"))) is None or not HISTORICAL_START_YEAR <= year <= HISTORICAL_END_YEAR)
    modern_bad_dates = sorted(identifier for identifier, row in modern.items() if (year := _date_year(row.get("date_issued"))) is not None and HISTORICAL_START_YEAR <= year <= HISTORICAL_END_YEAR)
    overlap_keys: dict[tuple[str, ...], dict[str, set[str]]] = defaultdict(lambda: {"modern": set(), "historical": set()})
    for family, corpus in (("modern", modern), ("historical", historical)):
      for row in corpus.values():
        identifier = _source_id(row)
        citation = _normalized_citation(row.get("citation"))
        if citation:
            overlap_keys[("citation", citation)][family].add(identifier)
        docket, date, name = (str(row.get(key) or "").strip().lower() for key in ("case_number", "date_issued", "case_name"))
        if docket and date and name:
            overlap_keys[("tuple", docket, date, name)][family].add(identifier)
    overlaps = [
        {"match_type": key[0], "value": list(key[1:]), "source_document_ids": sorted(families["modern"] | families["historical"]), "reviewed": "|".join(sorted(families["modern"] | families["historical"])) in reviewed_overlaps}
        for key, families in sorted(overlap_keys.items()) if families["modern"] and families["historical"]
    ]
    unresolved = [item for item in overlaps if not item["reviewed"]]
    records = sorted(combined.values(), key=_record_sort_key)
    report = {
        "modern_input_count": len(modern_rows), "historical_input_count": len(historical_rows),
        "modern_canonical_count": len(modern), "historical_canonical_count": len(historical),
        "combined_canonical_count": len(records), "duplicate_ids": ids_in_both,
        "modern_duplicate_resolution": modern_resolutions,
        "historical_duplicate_resolution": historical_resolutions,
        "collisions": collisions, "boundary_overlaps": overlaps,
        "unresolved_overlaps": unresolved, "historical_invalid_dates": historical_bad_dates,
        "modern_boundary_date_violations": modern_bad_dates,
        "safe_to_promote": not (collisions or unresolved or historical_bad_dates or modern_bad_dates),
    }
    return records, report


def write_combined(artifacts_root: Path, *, promote: bool = False, reviewed_overlaps: set[str] | None = None, modern_manifest: Path | None = None, date_overrides: Path | None = None) -> dict[str, Any]:
    root = Path(artifacts_root)
    modern_path = root / "compiled" / "case_digests.json"
    historical_path = root / "courtlistener" / "compiled" / "case_digests.json"
    if not modern_path.exists() or not historical_path.exists():
        raise IntegrationError("Both modern and historical compiled aggregates are required")
    date_overrides = date_overrides or root / "review" / "corpus_date_overrides.json"
    modern_rows = enrich_with_manifest(_rows_from_json(modern_path), modern_manifest, date_overrides)
    records, report = merge_corpora(modern_rows, _rows_from_json(historical_path), reviewed_overlaps)
    report["modern_manifest"] = str(modern_manifest) if modern_manifest else None
    report["date_overrides"] = str(date_overrides) if date_overrides.exists() else None
    combined_path = root / "compiled" / "combined_case_digests.json"
    _write_json(combined_path, {"record_count": len(records), "records": records})
    _write_json(root / "compiled" / "combined_merge_report.json", report)
    if promote:
        if not report["safe_to_promote"]:
            raise IntegrationError("Combined corpus has unreviewed conflicts; live aggregate was not replaced")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_artifacts(
            [modern_path, root / "compiled" / "research_index.db", root / "compiled" / "case_digests_fts.db"],
            root / "backups" / f"courtlistener_integration_{stamp}",
        )
        shutil.copy2(combined_path, modern_path)
    return report


def build_indexes(combined_path: Path, output_dir: Path) -> dict[str, int]:
    """Build the research, FTS, and citation-derived indexes from one input."""
    records = _rows_from_json(Path(combined_path))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    research_path, fts_path = output_dir / "research_index.db", output_dir / "case_digests_fts.db"
    for path in (research_path, fts_path):
        if path.exists(): path.unlink()
    with sqlite3.connect(research_path) as connection:
        connection.execute("CREATE TABLE cases (source_document_id TEXT PRIMARY KEY, case_number TEXT, case_name TEXT, citation TEXT, date_issued TEXT, text_path TEXT, external_ids TEXT, record_json TEXT)")
        connection.executemany("INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [(_source_id(row), str(row.get("case_number") or ""), str(row.get("case_name") or ""), str(row.get("citation") or ""), str(row.get("date_issued") or ""), str(row.get("text_path") or ""), json.dumps(row.get("external_ids") or {}, sort_keys=True), json.dumps(row, ensure_ascii=False, sort_keys=True)) for row in records])
        connection.execute("CREATE INDEX cases_date_idx ON cases(date_issued)")
    with sqlite3.connect(fts_path) as connection:
        connection.execute("CREATE VIRTUAL TABLE case_digests_fts USING fts5(source_document_id UNINDEXED, case_name, citation, summary, holdings, cited_propositions)")
        connection.executemany("INSERT INTO case_digests_fts VALUES (?, ?, ?, ?, ?, ?)", [(_source_id(row), str(row.get("case_name") or ""), str(row.get("citation") or ""), str(row.get("summary") or ""), json.dumps(row.get("holdings") or [], ensure_ascii=False), json.dumps(row.get("cited_propositions") or [], ensure_ascii=False)) for row in records])
    propositions, edges = [], []
    for row in records:
        source_id = _source_id(row)
        for proposition in row.get("cited_propositions") or []:
            propositions.append({"source_document_id": source_id, "proposition": proposition})
        for edge in row.get("citation_edges") or []:
            edges.append({"source_document_id": source_id, "edge": edge})
    _write_json(output_dir / "citation_propositions.json", propositions)
    _write_json(output_dir / "citation_edges.json", edges)
    return {"records": len(records), "citation_propositions": len(propositions), "citation_edges": len(edges)}


def backup_artifacts(source_paths: Iterable[Path], backup_dir: Path) -> dict[str, str]:
    """Copy current generated artifacts before a switch and return SHA-256 hashes."""
    import hashlib
    backup_dir = Path(backup_dir); backup_dir.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for source in source_paths:
        source = Path(source)
        if source.exists() and source.is_file():
            destination = backup_dir / source.name
            shutil.copy2(source, destination)
            hashes[source.name] = hashlib.sha256(destination.read_bytes()).hexdigest()
    _write_json(backup_dir / "SHA256SUMS.json", hashes)
    return hashes
