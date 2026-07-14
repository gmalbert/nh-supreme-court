from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from scripts.build_oral_argument_index import build_index
from scripts.refresh_oral_arguments import validate_payload
from utils.data_loader import load_oral_arguments
from utils.oral_arguments import (
    collection_statistics,
    find_argument_for_docket,
    has_confirmed_argument_date,
    make_search_snippet,
    normalize_docket_numbers,
    search_oral_arguments,
)


class OralArgumentHelperTests(unittest.TestCase):
    def test_excludes_term_start_default_dates_from_statistics(self):
        self.assertFalse(
            has_confirmed_argument_date(
                {"argument_date": "2015-10-01", "term_year": 2015}
            )
        )
        self.assertTrue(
            has_confirmed_argument_date(
                {"argument_date": "2015-10-15", "term_year": 2015}
            )
        )

    def test_repository_uses_confirmed_dates_and_normalized_state_titles(self):
        data_dir = Path(__file__).resolve().parents[1] / "data" / "processed"
        records = build_index(data_dir / "oral_arguments")
        self.assertTrue(all(has_confirmed_argument_date(record) for record in records))
        self.assertFalse(
            any(
                re.match(r"^New Hampshire\s+(?:Versus|v\.?)\s+", record["case_name"], re.IGNORECASE)
                for record in records
            )
        )

    def test_normalizes_combined_docket(self):
        self.assertEqual(
            normalize_docket_numbers("2024-0722-2024-0723"),
            ["2024-0722", "2024-0723"],
        )

    def test_search_prioritizes_exact_docket_and_searches_transcript(self):
        records = [
            {
                "case_number": "2025-0001",
                "case_name": "Alpha v. Beta",
                "argument_date": "2026-01-01",
                "transcript_text": "The court discussed zoning and municipal authority.",
            },
            {
                "case_number": "2025-0002",
                "case_name": "Gamma v. Delta",
                "argument_date": "2026-02-01",
                "transcript_text": "No related phrase appears here.",
            },
        ]
        self.assertEqual(search_oral_arguments(records, "2025-0002")[0]["case_number"], "2025-0002")
        self.assertEqual(search_oral_arguments(records, "zoning")[0]["case_number"], "2025-0001")

    def test_snippet_centers_on_query(self):
        snippet = make_search_snippet("Opening words " + ("filler " * 80) + "needle nearby words", "needle", 40)
        self.assertIn("needle", snippet)
        self.assertTrue(snippet.startswith("..."))

    def test_find_argument_matches_secondary_combined_docket(self):
        records = [{"case_number": "2024-0722-2024-0723", "docket_numbers": ["2024-0722", "2024-0723"]}]
        match = find_argument_for_docket(records, "2024-0723")
        self.assertIsNotNone(match)
        self.assertEqual(match["case_number"], "2024-0722-2024-0723")

    def test_collection_statistics(self):
        stats = collection_statistics(
            [
                {"duration_seconds": 600, "word_count": 1000},
                {"duration_seconds": 1200, "word_count": 2000},
            ]
        )
        self.assertEqual(stats["argument_count"], 2)
        self.assertEqual(stats["total_duration_seconds"], 1800)
        self.assertEqual(stats["median_duration_seconds"], 900)
        self.assertEqual(stats["total_word_count"], 3000)


class OralArgumentPayloadTests(unittest.TestCase):
    def _write_fixture(
        self,
        data_dir: Path,
        include_transcripts: bool = True,
        include_case_json: bool = True,
    ) -> None:
        case_number = "2025-0001"
        record = {
            "case_number": case_number,
            "case_name": "Alpha v. Beta",
            "argument_date": "2026-01-01",
            "duration_seconds": 600,
        }
        (data_dir / "oral_arguments" / "markdown").mkdir(parents=True)
        (data_dir / "oral_arguments" / "text").mkdir(parents=True)
        (data_dir / "oral_arguments.json").write_text(json.dumps([record]), encoding="utf-8")
        if include_case_json:
            (data_dir / "oral_arguments" / f"{case_number}.json").write_text(
                json.dumps({**record, "transcript_text": "A short transcript"}),
                encoding="utf-8",
            )
        if include_transcripts:
            (data_dir / "oral_arguments" / "markdown" / f"{case_number}.md").write_text(
                "# Alpha v. Beta\n\nA short transcript", encoding="utf-8"
            )
            (data_dir / "oral_arguments" / "text" / f"{case_number}.txt").write_text(
                "A short transcript", encoding="utf-8"
            )

    def test_validator_builds_public_stats_without_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self._write_fixture(data_dir)
            report = validate_payload(data_dir=data_dir, archive_root=None)
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["public_stats"][0]["word_count"], 3)
            self.assertNotIn("operational_quality_score", report["public_stats"][0])

    def test_validator_reports_missing_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self._write_fixture(data_dir, include_transcripts=False)
            report = validate_payload(data_dir=data_dir, archive_root=None)
            self.assertTrue(any("Missing artifact" in error for error in report["errors"]))

    def test_validator_allows_gitignored_per_case_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self._write_fixture(data_dir, include_case_json=False)
            report = validate_payload(data_dir=data_dir, archive_root=None)
            self.assertEqual(report["errors"], [])

    def test_validator_warns_for_docket_shared_by_argument_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self._write_fixture(data_dir)
            records = json.loads((data_dir / "oral_arguments.json").read_text(encoding="utf-8"))
            combined = {**records[0], "case_number": "2025-0001-2025-0002"}
            records.append(combined)
            (data_dir / "oral_arguments.json").write_text(json.dumps(records), encoding="utf-8")
            for suffix in ("md", "txt"):
                directory = "markdown" if suffix == "md" else "text"
                (data_dir / "oral_arguments" / directory / f"{combined['case_number']}.{suffix}").write_text(
                    "A short transcript", encoding="utf-8"
                )

            report = validate_payload(data_dir=data_dir, archive_root=None)

            self.assertEqual(report["errors"], [])
            self.assertTrue(any("more than one argument record" in warning for warning in report["warnings"]))

    def test_repository_loader_returns_all_public_records(self):
        records = load_oral_arguments()
        index_path = Path(__file__).resolve().parents[1] / "data" / "processed" / "oral_arguments.json"
        expected_records = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(len(records), len(expected_records))
        self.assertTrue(all(row.get("word_count") for row in records))
        self.assertTrue(all(row.get("docket_numbers") for row in records))
        self.assertTrue(all(not any(key.startswith("granite_export_") for key in row) for row in records))


if __name__ == "__main__":
    unittest.main()
