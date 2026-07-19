from __future__ import annotations

import pandas as pd

from utils.case_resolution import (
    argument_resolution_summary,
    assess_unmatched_arguments,
    disposition_source_summary,
)


def test_argument_resolution_matches_combined_dockets_and_preserves_multiple_results():
    arguments = [
        {"case_number": "2024-0001-2024-0002", "docket_numbers": ["2024-0001", "2024-0002"]},
        {"case_number": "2024-0003"},
        {"case_number": "2024-0004"},
    ]
    orders = pd.DataFrame([
        {"case_number": "2024-0002", "order_source": "case_order"},
        {"case_number": "2024-0004", "order_source": "3jx_order"},
    ])
    opinions = pd.DataFrame([{"case_number": "2024-0004"}])

    result = argument_resolution_summary(arguments, orders, opinions)

    assert result["resolution"].tolist() == ["case_order", "unmatched", "multiple"]


def test_disposition_summary_counts_unique_dockets_by_source():
    arguments = [{"case_number": "2024-0001"}, {"case_number": "2024-0002"}]
    orders = pd.DataFrame([
        {"case_number": "2024-0001", "order_source": "case_order"},
        {"case_number": "2024-0003", "order_source": "3jx_order"},
    ])
    opinions = pd.DataFrame([{"case_number": "2024-0002"}, {"case_number": "2024-0003"}])

    result = disposition_source_summary(arguments, {"2024-0002": [{}]}, orders, opinions)

    assert result.to_dict("records") == [
        {"Disposition": "Case orders", "With oral argument": 1, "With published brief counsel": 0},
        {"Disposition": "3JX orders", "With oral argument": 0, "With published brief counsel": 0},
        {"Disposition": "Opinions", "With oral argument": 1, "With published brief counsel": 1},
    ]


def test_argument_resolution_flags_same_date_title_candidate_for_review():
    arguments = [{"case_number": "2024-0001", "case_name": "Alpha v. Beta", "argument_date": "2025-01-10"}]
    opinions = pd.DataFrame([
        {"case_number": "pdf-alpha", "case_name": "Alpha v. Beta", "date_argued": "2025-01-10"}
    ])

    result = argument_resolution_summary(arguments, pd.DataFrame(), opinions)

    assert result.loc[0, "resolution"] == "needs_review"


def test_unmatched_assessment_keeps_caption_metadata_separate_from_matching():
    arguments = [
        {"case_number": "2024-0001", "term_year": 2026, "case_name": "Current case"},
        {"case_number": "2015-0001", "term_year": 2015, "case_name": "Good morning, counsel"},
        {"case_number": "2015-0002", "term_year": 2015, "case_name": "Historic case"},
        {"case_number": "2018-0068", "term_year": 2019, "case_name": "State v. Maritell-Saintill"},
    ]
    resolutions = pd.DataFrame({"case_number": [a["case_number"] for a in arguments], "resolution": "unmatched"})

    result = assess_unmatched_arguments(resolutions, arguments, {"2018-0068"}).set_index("case_number")

    assert result.loc["2024-0001", "assessment"] == "current_term_pending"
    assert result.loc["2015-0001", "assessment"] == "historical_no_disposition_in_corpus"
    assert result.loc["2015-0001", "caption_metadata_status"] == "transcript_title_needs_roster_backfill"
    assert result.loc["2015-0002", "assessment"] == "historical_no_disposition_in_corpus"
    assert result.loc["2018-0068", "assessment"] == "official_pdf_pending_ingestion"


def test_unmatched_assessment_respects_verified_pending_dockets_before_term_heuristics():
    arguments = [{"case_number": "2024-0711-2025-0079", "term_year": 2025, "case_name": "Meehan"}]
    resolutions = pd.DataFrame({"case_number": ["2024-0711-2025-0079"], "resolution": ["unmatched"]})

    result = assess_unmatched_arguments(
        resolutions, arguments, pending_dockets={"2024-0711", "2025-0079"}
    )

    assert result.loc[0, "assessment"] == "pending_after_oral_argument"
