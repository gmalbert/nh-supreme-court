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


def test_attorney_builder_uses_pdf_roster_without_transcript_volume(monkeypatch, tmp_path):
    from scripts import extract_attorney_stats as builder
    roster_file = tmp_path / 'oral_argument_roster.json'
    roster_file.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(builder, 'PDF_ORAL_ROSTER_FILE', roster_file)
    monkeypatch.setattr(builder, 'TRANSCRIPTS_DIR', tmp_path / 'missing-transcripts')
    monkeypatch.setattr(builder, 'load_oral_arguments', lambda: {'2024-0001': {'duration_seconds': 3600, 'argument_date': '2024-02-01'}})
    monkeypatch.setattr(builder, 'load_attorney_name_map', lambda: {'A. Counsel': 'Alice Counsel'})
    monkeypatch.setattr(builder, 'load_firm_name_map', lambda: {'Firm': 'Firm LLP'})
    monkeypatch.setattr(builder, 'load_public_affiliation_map', lambda: {})
    monkeypatch.setattr(builder, 'load_case_attorney_overrides', lambda: {})
    monkeypatch.setattr(builder, 'load_pdf_attorney_roster_overrides', lambda: {})
    monkeypatch.setattr(builder, 'load_approved_oral_advocate_facts', lambda: {})
    monkeypatch.setattr(builder, 'load_pdf_oral_rosters', lambda: {'2024-0001': [
        {'name': 'A. Counsel', 'firm': 'Firm', 'side': 'appellant'},
        {'name': 'A. Counsel', 'firm': 'Firm', 'side': 'appellant'},
        {'name': 'Bob Counsel', 'firm': 'Firm', 'side': 'appellee'},
    ]})
    result = builder.extract_attorney_data()
    assert [row['name'] for row in result['case_attorneys']['2024-0001']] == ['Alice Counsel', 'Bob Counsel']
    assert result['attorney_stats'][0]['total_duration_hours'] == 1
    assert result['firm_stats'][0]['total_arguments'] == 1
    assert result['firm_stats'][0]['unique_attorneys'] == 2


def test_attorney_builder_does_not_overwrite_directory_with_empty_roster(monkeypatch, tmp_path):
    from scripts import extract_attorney_stats as builder
    import pytest
    roster = tmp_path / 'roster.json'
    roster.write_text('{}', encoding='utf-8')
    output = tmp_path / 'attorney_stats.json'
    output.write_text('existing data', encoding='utf-8')
    monkeypatch.setattr(builder, 'PDF_ORAL_ROSTER_FILE', roster)
    monkeypatch.setattr(builder, 'OUTPUT_FILE', output)
    monkeypatch.setattr(builder, 'extract_attorney_data', lambda: {'case_attorneys': {}, 'attorney_stats': [], 'firm_stats': []})
    with pytest.raises(SystemExit, match='refusing to overwrite'):
        builder.main()
    assert output.read_text(encoding='utf-8') == 'existing data'


def test_interaction_summary_counts_only_analyzed_rosters(monkeypatch, tmp_path):
    import json
    from scripts import analyze_attorney_justice_interactions as analysis
    args = tmp_path / 'arguments.json'
    args.write_text(json.dumps([{'case_number':'a','argument_date':'2024-01-01'}, {'case_number':'b','argument_date':'2024-01-02'}]), encoding='utf-8')
    roster = tmp_path / 'attorneys.json'
    roster.write_text(json.dumps({'case_attorneys':{'a':[{'name':'Counsel'}]}}), encoding='utf-8')
    monkeypatch.setattr(analysis, 'ORAL_ARGUMENTS_FILE', args)
    monkeypatch.setattr(analysis, 'ATTORNEY_STATS_FILE', roster)
    monkeypatch.setattr(analysis, 'load_justices', lambda:[{'display_name':'Justice','date_appointed':'2020-01-01','date_retired':None}])
    result = analysis.analyze_interactions()
    assert result['summary']['total_arguments_analyzed'] == 1
    assert result['justice_interactions'][0]['total_arguments'] == 1
    assert result['attorney_interactions'][0]['interactions'] == [{'justice':'Justice','arguments':1}]
