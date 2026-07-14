"""Regression tests for the reviewed law-firm directory."""

import csv

from scripts.extract_attorney_stats import FIRM_SOURCE_FILE, load_firm_name_map


def test_csv_preserves_migrated_non_firm_aliases_without_admitting_them_as_firms():
    with FIRM_SOURCE_FILE.open(newline="", encoding="utf-8") as source:
        rows = {row["short_name"]: row for row in csv.DictReader(source)}

    assert rows["ACLU-NH"]["full_name"] == "American Civil Liberties Union - New Hampshire"
    assert rows["CAB"]["full_name"] == "Compensation Appeals Board"
    assert rows["NEA-NH"]["full_name"] == "National Education Association - New Hampshire"

    firms = load_firm_name_map()
    assert "ACLU-NH" not in firms
    assert "CAB" not in firms
    assert "NEA-NH" not in firms


def test_only_reviewed_csv_firms_can_enter_the_directory():
    firms = load_firm_name_map()

    assert firms["S&G"] == "Shaheen & Gordon, P.A."
    assert firms["MGR&M"] == "McLane Middleton, Professional Association"
    for pdf_fragment in ("General", "Board)", "petitioner", "Trust"):
        assert pdf_fragment not in firms
