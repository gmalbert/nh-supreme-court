"""Run the retrieval evaluation suite.

Reports the metrics described in section 23 of the roadmap.

Usage:
    python scripts/evaluate_retrieval.py --suite tests/retrieval/eval_queries.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from utils.retrieval.service import get_service_for_session  # noqa: E402


def load_queries(path: Path) -> list[dict]:
    queries = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            queries.append(json.loads(line))
    return queries


def _match_name(actual: str, expected: str) -> bool:
    a = (actual or "").casefold()
    e = (expected or "").casefold()
    if not a or not e:
        return False
    return e in a or a in e


def evaluate(queries: Iterable[dict], service) -> dict:
    queries = list(queries)
    metrics = {
        "total": 0,
        "exact_top1": 0,
        "exact_top1_total": 0,
        "recall_top5": 0,
        "recall_top5_total": 0,
        "recall_top10": 0,
        "recall_top10_total": 0,
        "field_coverage": 0,
        "field_coverage_total": 0,
    }
    rows = []
    for q in queries:
        metrics["total"] += 1
        response = service.retrieve(q["query"], limit=10)
        cases = list(response.cases)
        names = [c.name for c in cases]
        if "must_rank_top1" in q:
            metrics["exact_top1_total"] += 1
            top1 = q["must_rank_top1"][0]
            if any(_match_name(n, top1) for n in names[:1]):
                metrics["exact_top1"] += 1
        if "must_rank_top10" in q:
            metrics["recall_top10_total"] += 1
            ok = sum(
                1
                for expected in q["must_rank_top10"]
                if any(_match_name(n, expected) for n in names)
            )
            metrics["recall_top10"] += ok / len(q["must_rank_top10"])
        if "must_rank_top5" in q:
            metrics["recall_top5_total"] += 1
            ok = sum(
                1
                for expected in q["must_rank_top5"]
                if any(_match_name(n, expected) for n in names[:5])
            )
            metrics["recall_top5"] += ok / len(q["must_rank_top5"])
        if "required_fields" in q:
            metrics["field_coverage_total"] += 1
            if (
                response.sufficient
                or all(field not in response.missing_fields for field in q["required_fields"])
            ):
                metrics["field_coverage"] += 1
        rows.append(
            {
                "id": q.get("id", ""),
                "query": q["query"],
                "returned": names[:5],
                "sufficient": response.sufficient,
                "missing": list(response.missing_fields),
            }
        )
    return {"metrics": metrics, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        default=str(ROOT / "tests" / "retrieval" / "eval_queries.jsonl"),
        help="JSONL file of evaluation queries",
    )
    args = parser.parse_args()
    suite_path = Path(args.suite)
    if not suite_path.exists():
        print(f"Suite not found: {suite_path}")
        sys.exit(1)

    queries = load_queries(suite_path)
    service = get_service_for_session()
    if not service.is_ready():
        print("Retrieval service is not ready. Build the corpus first.")
        sys.exit(1)

    report = evaluate(queries, service)
    print(json.dumps(report["metrics"], indent=2))
    out_path = ROOT / "docs" / "retrieval-baseline.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as handle:
        handle.write("# Retrieval baseline report\n\n")
        handle.write("```json\n")
        handle.write(json.dumps(report["metrics"], indent=2))
        handle.write("\n```\n\n")
        handle.write("## Per-query rows\n\n")
        handle.write("| id | top5 | sufficient | missing |\n")
        handle.write("|---|---|---|---|\n")
        for row in report["rows"]:
            handle.write(
                f"| {row['id']} | {row['returned']} | {row['sufficient']} | "
                f"{row['missing']} |\n"
            )
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()