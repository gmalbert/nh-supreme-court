"""Build public oral-argument statistics and validate the processed payload."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.oral_arguments import normalize_docket_numbers

DATA_DIR = ROOT / "data" / "processed"
DEFAULT_ARCHIVE = ROOT / "nh-supreme-court-transcripts"
PUBLIC_STATS_PATH = DATA_DIR / "oral_argument_stats.json"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _is_absolute_path(value: object) -> bool:
    text = str(value or "")
    return PurePosixPath(text).is_absolute() or PureWindowsPath(text).is_absolute()


def _archive_records(archive_root: Path | None) -> tuple[dict[str, dict], dict[str, dict]]:
    metadata: dict[str, dict] = {}
    stats: dict[str, dict] = {}
    if archive_root is None or not archive_root.exists():
        return metadata, stats
    for path in archive_root.glob("20??/*/*/metadata.json"):
        try:
            record = _read_json(path)
            metadata[str(record.get("docket_number", ""))] = record
        except (OSError, json.JSONDecodeError):
            continue
    for path in archive_root.glob("20??/*/*/public/transcript_stats.json"):
        try:
            record = _read_json(path)
            stats[str(record.get("docket_number", ""))] = record
        except (OSError, json.JSONDecodeError):
            continue
    return metadata, stats


def validate_payload(
    data_dir: Path = DATA_DIR,
    archive_root: Path | None = DEFAULT_ARCHIVE,
) -> dict[str, object]:
    """Validate processed artifacts and return errors, warnings, and public stats."""
    errors: list[str] = []
    warnings: list[str] = []
    public_stats: list[dict[str, object]] = []
    index_path = data_dir / "oral_arguments.json"
    try:
        records = _read_json(index_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"errors": [f"Cannot read {index_path}: {exc}"], "warnings": [], "public_stats": []}
    if not isinstance(records, list):
        return {"errors": ["oral_arguments.json must contain a JSON array"], "warnings": [], "public_stats": []}

    archive_metadata, archive_stats = _archive_records(archive_root)
    seen_keys: set[str] = set()
    all_dockets: set[str] = set()
    quality_counts: Counter[str] = Counter()
    flagged: list[str] = []
    absolute_source_paths = 0
    derived_word_counts = 0

    for position, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            errors.append(f"Record {position} is not a JSON object")
            continue
        case_number = str(record.get("case_number", "")).strip()
        if not case_number:
            errors.append(f"Record {position} is missing case_number")
            continue
        if case_number in seen_keys:
            errors.append(f"Duplicate case_number: {case_number}")
        seen_keys.add(case_number)
        dockets = normalize_docket_numbers(case_number)
        if not dockets:
            errors.append(f"Invalid docket key: {case_number}")
        for docket in dockets:
            if docket in all_dockets:
                errors.append(f"Docket appears in more than one record: {docket}")
            all_dockets.add(docket)

        case_json_path = data_dir / "oral_arguments" / f"{case_number}.json"
        markdown_path = data_dir / "oral_arguments" / "markdown" / f"{case_number}.md"
        text_path = data_dir / "oral_arguments" / "text" / f"{case_number}.txt"
        for path in (case_json_path, markdown_path, text_path):
            if not path.exists():
                errors.append(f"Missing artifact for {case_number}: {path.relative_to(data_dir)}")

        case_record: dict = {}
        if case_json_path.exists():
            try:
                case_record = _read_json(case_json_path)
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"Malformed per-case JSON for {case_number}: {exc}")
            if case_record and str(case_record.get("case_number", "")) != case_number:
                errors.append(f"Per-case docket mismatch for {case_number}")
            for field in ("case_name", "argument_date"):
                if case_record and str(case_record.get(field, "")) != str(record.get(field, "")):
                    errors.append(f"Per-case {field} mismatch for {case_number}")
        if text_path.exists() and not text_path.read_text(encoding="utf-8").strip():
            errors.append(f"Empty transcript text for {case_number}")
        if markdown_path.exists() and not markdown_path.read_text(encoding="utf-8").strip():
            errors.append(f"Empty transcript Markdown for {case_number}")

        for field in ("granite_export_json", "granite_export_text", "granite_export_markdown"):
            if _is_absolute_path(record.get(field)):
                absolute_source_paths += 1

        metadata = archive_metadata.get(case_number)
        score = archive_stats.get(case_number)
        if archive_root is not None and archive_root.exists():
            if metadata is None:
                errors.append(f"Archive metadata missing for {case_number}")
            elif str(metadata.get("argument_date", "")) != str(record.get("argument_date", "")):
                errors.append(f"Archive argument_date mismatch for {case_number}")
            if score is None:
                errors.append(f"Archive transcript_stats missing for {case_number}")

        metrics = (score or {}).get("metrics") or {}
        duration = metrics.get("duration_seconds", record.get("duration_seconds"))
        word_count = metrics.get("word_count")
        if word_count is None and text_path.exists():
            word_count = len(text_path.read_text(encoding="utf-8").split())
            derived_word_counts += 1
        words_per_minute = metrics.get("words_per_minute")
        if words_per_minute is None and duration and word_count is not None:
            words_per_minute = round(float(word_count) / (float(duration) / 60), 2)
        if duration is None or word_count is None or words_per_minute is None:
            errors.append(f"Cannot build public statistics for {case_number}")
        else:
            public_stats.append(
                {
                    "case_number": case_number,
                    "argument_date": str(record.get("argument_date", "")),
                    "duration_seconds": round(float(duration), 3),
                    "word_count": int(word_count),
                    "words_per_minute": round(float(words_per_minute), 2),
                }
            )

        if score:
            priority = str(score.get("review_priority", "unknown"))
            quality_counts[priority] += 1
            if priority != "low":
                flagged.append(case_number)

    if archive_root is not None and archive_root.exists():
        for temp_path in archive_root.glob("20??/**/*.temp.*"):
            warnings.append(f"Incomplete temporary archive artifact: {temp_path.relative_to(archive_root)}")
    if absolute_source_paths:
        warnings.append(
            f"Ignored {absolute_source_paths} legacy absolute export paths; runtime paths are repo-relative"
        )
    if derived_word_counts:
        warnings.append(
            f"Derived word counts for {derived_word_counts} records because archive stats were unavailable"
        )

    return {
        "errors": errors,
        "warnings": warnings,
        "public_stats": sorted(public_stats, key=lambda row: (row["argument_date"], row["case_number"])),
        "quality_counts": dict(sorted(quality_counts.items())),
        "flagged_dockets": sorted(flagged),
        "record_count": len(records),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate without rewriting public statistics")
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()

    report = validate_payload(archive_root=args.archive_root)
    if args.check and not report["errors"]:
        try:
            committed_stats = _read_json(PUBLIC_STATS_PATH)
        except (OSError, json.JSONDecodeError) as exc:
            report["errors"].append(f"Cannot read committed public statistics: {exc}")
        else:
            required_fields = {
                "case_number", "argument_date", "duration_seconds", "word_count", "words_per_minute"
            }
            expected_dockets = {str(row.get("case_number", "")) for row in report["public_stats"]}
            if not isinstance(committed_stats, list) or any(
                not isinstance(row, dict) or set(row) != required_fields for row in committed_stats
            ):
                report["errors"].append("oral_argument_stats.json has an invalid public schema")
            elif {str(row.get("case_number", "")) for row in committed_stats} != expected_dockets:
                report["errors"].append("oral_argument_stats.json docket coverage is stale")
            elif args.archive_root.exists() and committed_stats != report["public_stats"]:
                report["errors"].append(
                    "oral_argument_stats.json is stale; run python scripts/refresh_oral_arguments.py"
                )
    if not args.check and not report["errors"]:
        PUBLIC_STATS_PATH.write_text(
            json.dumps(report["public_stats"], indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {len(report['public_stats'])} records to {PUBLIC_STATS_PATH.relative_to(ROOT)}")

    print(f"Validated {report.get('record_count', 0)} oral arguments")
    if report.get("quality_counts"):
        print(f"Internal review priorities: {report['quality_counts']}")
        print(f"Flagged dockets: {', '.join(report['flagged_dockets']) or 'none'}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    for error in report["errors"]:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
