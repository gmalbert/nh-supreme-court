"""Build a documentary review queue for oral arguments without published PDFs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.case_resolution import argument_resolution_summary, assess_unmatched_arguments
from utils.dockets import apply_docket_crosswalk, parse_docket_numbers


DATA_DIR = ROOT / "data" / "processed"
OUTPUT_PATH = DATA_DIR / "unmatched_argument_review_queue.csv"
PENDING_CASES_PATH = ROOT / "data" / "pending_oral_argument_cases.csv"
CASE_STATUS_REPORT_URL = "https://www.courts.nh.gov/our-courts/supreme-court/case-status-report"


def build_queue() -> pd.DataFrame:
    with (DATA_DIR / "oral_arguments.json").open(encoding="utf-8") as handle:
        arguments = json.load(handle)
    opinions = pd.read_csv(DATA_DIR / "opinions.csv", low_memory=False)
    orders = pd.read_csv(DATA_DIR / "case_orders.csv", low_memory=False)
    orders["order_source"] = "case_order"
    jx_orders = pd.read_csv(DATA_DIR / "3jx_orders.csv", low_memory=False)
    jx_orders["order_source"] = "3jx_order"
    crosswalk = pd.read_csv(DATA_DIR / "case_docket_crosswalk.csv", dtype=str).fillna("")
    dispositions = pd.concat(
        [
            apply_docket_crosswalk(orders, crosswalk, "case_order"),
            apply_docket_crosswalk(jx_orders, crosswalk, "3jx_order"),
        ],
        ignore_index=True,
    )
    opinion_dockets = apply_docket_crosswalk(opinions, crosswalk, "opinion")
    resolutions = argument_resolution_summary(arguments, dispositions, opinion_dockets)
    pending = pd.read_csv(PENDING_CASES_PATH, dtype=str).fillna("")
    pending_dockets = {
        docket
        for value in pending.get("case_number", pd.Series(dtype=str))
        for docket in parse_docket_numbers(value)
    }
    assessment = assess_unmatched_arguments(resolutions, arguments, pending_dockets=pending_dockets)
    historical = assessment[assessment["assessment"] == "historical_no_disposition_in_corpus"].copy()
    historical["published_pdf_status"] = "no_published_pdf_disposition_found"
    historical["docket_status"] = "needs_court_file_review"
    historical["inventory_evidence"] = (
        "No exact docket in official opinion inventory (2002–2024), "
        "case-order inventory (2014–2024), or local 3JX orders."
    )
    historical["case_status_report_url"] = CASE_STATUS_REPORT_URL
    historical["verified_status_source_url"] = ""
    historical["review_notes"] = "Do not infer a result from title or date similarity."
    columns = [
        "case_number",
        "argument_date",
        "term_year",
        "case_name",
        "published_pdf_status",
        "docket_status",
        "inventory_evidence",
        "case_status_report_url",
        "verified_status_source_url",
        "review_notes",
    ]
    return historical[columns].sort_values(["argument_date", "case_number"])


def main() -> None:
    queue = build_queue()
    queue.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    print(f"Wrote {len(queue)} docket-status review rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
