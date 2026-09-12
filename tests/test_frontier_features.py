from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from scripts.weekly_digest import configured_recipients

from utils.authority_graph import (
    Treatment,
    classify_treatment,
    controlling_treatments,
    extract_treatments_for_opinion,
    load_treatment_classifier,
    train_treatment_classifier,
)
from utils.claim_verifier import publishable, verify_answer, verify_claim
from utils.court_calendar import (
    compute_filing_deadline,
    parse_oral_argument_schedule,
)
from utils.data_releases import create_release, load_latest_manifest, verify_release
from utils.evaluation_gates import gate_release, validate_gold_set
from utils.issue_lifecycle import (
    build_issue_threads,
    holding_diff,
    stable_issue_url,
)
from utils.legal_glossary import annotate_terms_html, find_terms, get_definition
from utils.opinion_viewer import extract_key_passages
from utils.privacy_telemetry import record_event, sanitize_properties
from utils.provenance import (
    load_observations,
    observation_from_record,
    rank_review_queue,
    record_review,
    upsert_observations,
)
from utils.readability import add_readability_scores, compute_readability
from utils.research_workspace import (
    add_item,
    add_note,
    export_packet_json,
    export_packet_markdown,
    new_workspace,
    resolve_workspace,
    validate_workspace,
)
from utils.roadmap_analytics import (
    attorney_win_rates,
    build_case_timeline,
    disposition_trends,
    justice_topic_voting,
    tag_bar_exam_relevance,
)
from utils.temporal_research import (
    filter_as_of,
    parse_as_of_date,
    temporal_leakage_rate,
)
from utils.topic_labeler import auto_label_topic, batch_label_opinions
from utils.transcript_search import (
    build_transcript_index,
    search_transcripts,
    timestamp_url,
)


def test_authority_classifier_and_time_filter():
    assert classify_treatment("We distinguish Smith on its facts")[0] == "distinguished"
    edges = [
        Treatment(
            "2020-0001",
            "2010-0001",
            "followed",
            0.9,
            0,
            40,
            "We follow the earlier rule in Smith.",
            date(2020, 1, 1),
        ),
        Treatment(
            "2025-0001",
            "2010-0001",
            "overruled",
            0.99,
            0,
            45,
            "The earlier rule is expressly overruled.",
            date(2025, 1, 1),
        ),
    ]
    result = controlling_treatments(edges, "2010-0001", date(2022, 1, 1))
    assert [item.label for item in result] == ["followed"]


def test_authority_extraction_preserves_span():
    text = "Background. We distinguish 123 N.H. 456 because the facts differ."
    citation = {
        "unresolved": [
            {
                "text": "123 N.H. 456",
                "start_pos": text.index("123"),
                "end_pos": text.index("456") + 3,
            }
        ]
    }
    result = extract_treatments_for_opinion(
        {"case_number": "2024-0001", "date_issued": "2024-01-02"},
        citation,
        text,
    )
    assert result[0].label == "distinguished"
    assert "distinguish" in result[0].evidence_text
    assert result[0].display_label == "distinguished"


def test_treatment_classifier_trains_only_reviewed_examples(tmp_path):
    examples = [
        {"text": "The earlier analytical framework is persuasive here.", "label": "followed"},
        {"text": "We endorse the prior framework for this dispute.", "label": "followed"},
        {"text": "The earlier decision arose in a materially different setting.", "label": "distinguished"},
        {"text": "Different facts make the earlier framework inapplicable.", "label": "distinguished"},
        {"text": "This unreviewed row must be excluded.", "label": "limited", "reviewed": False},
    ]
    path = tmp_path / "treatment_model.joblib"
    artifact = train_treatment_classifier(examples, path)
    assert artifact["training_rows"] == 4
    loaded = load_treatment_classifier(path)
    label, confidence = classify_treatment(
        "We endorse the earlier analytical framework.", loaded
    )
    assert label in {"followed", "distinguished"}
    assert 0.0 <= confidence <= 1.0


def test_claim_verifier_removes_unsupported_claims():
    supported = "The court affirmed the judgment after applying de novo review."
    unsupported = "The court awarded punitive damages to the plaintiff."
    sources = [
        {
            "case_number": "2024-0001",
            "text": supported + " No damages were discussed.",
        }
    ]
    result = verify_answer(f"{supported} {unsupported}", sources)
    assert supported in result.publishable_text
    assert unsupported not in result.publishable_text
    assert len(result.verified_claims) == 1
    assert result.unsupported_claim_rate == pytest.approx(0.5)


def test_claim_publishability_requires_span_length():
    short = verify_claim(
        "The court affirmed.",
        [{"case_number": "x", "text": "The court affirmed."}],
    )
    assert not publishable(short)


def test_provenance_database_and_review_queue(tmp_path):
    record = {
        "case_number": "2024-0001",
        "outcome": "affirmed",
        "pdf_url": "https://example.test/opinion.pdf",
        "parse_confidence": 0.4,
        "parse_version": "parser-v1",
    }
    observation = observation_from_record(record, "outcome")
    path = tmp_path / "provenance.sqlite"
    assert upsert_observations(path, [observation]) == 1
    frame = load_observations(path)
    queue = rank_review_queue(frame, {"outcome": 10})
    assert queue.iloc[0]["review_priority"] == pytest.approx(6.0)
    record_review(
        path,
        record_id="2024-0001",
        field_name="outcome",
        source_sha256=observation.source_sha256,
        extractor_version="parser-v1",
        reviewed_value="reversed",
    )
    assert load_observations(path).iloc[0]["reviewed_value_json"] == '"reversed"'


def test_issue_lifecycle_and_diff():
    opinions = pd.DataFrame(
        [
            {
                "case_number": "2020-1",
                "case_name": "Alpha",
                "date_issued": "2020-01-01",
                "topics": ["Search and Seizure"],
                "summary_paragraph": "A warrant is generally required.",
                "outcome": "affirmed",
                "has_dissent": False,
            },
            {
                "case_number": "2022-1",
                "case_name": "Beta",
                "date_issued": "2022-01-01",
                "topics": ["Search and Seizure"],
                "summary_paragraph": "A warrant is required unless an exception applies.",
                "outcome": "reversed",
                "has_dissent": True,
            },
        ]
    )
    threads = build_issue_threads(opinions, as_of=date(2023, 1, 1))
    assert len(threads) == 1
    assert threads[0].unresolved_split
    assert "**+unless**" in holding_diff(
        threads[0].states[0].rule_text, threads[0].states[1].rule_text
    )
    assert "issue=search-and-seizure" in stable_issue_url(
        threads[0].issue_id, date(2023, 1, 1)
    )


def test_workspace_stores_offsets_and_resolves_at_export():
    workspace = new_workspace("hash-123")
    workspace = add_item(
        workspace,
        case_id="2024-1",
        kind="holding",
        start=4,
        end=15,
        source_url="https://example.test",
    )
    workspace = add_note(workspace, "Compare this holding.")
    validate_workspace(workspace)
    resolved = resolve_workspace(
        workspace,
        lambda case_id: {
            "case_name": "State v. Example",
            "citation": "180 N.H. 1",
            "text": "The court affirmed the judgment.",
        },
    )
    assert resolved["items"][0]["source_span"] == "court affir"
    assert b'"corpus_version": "hash-123"' in export_packet_json(resolved)
    assert "Machine-readable appendix" in export_packet_markdown(resolved)


def test_versioned_release_round_trip(tmp_path):
    opinions = pd.DataFrame(
        [
            {
                "case_number": "2024-1",
                "date_issued": "2024-01-01",
                "pdf_url": "https://example.test/1.pdf",
            },
            {
                "case_number": "2024-2",
                "date_issued": "2024-02-01",
                "pdf_url": "https://example.test/2.pdf",
            },
        ]
    )
    manifest_path = create_release(
        opinions,
        output_root=tmp_path,
        release_id="2024-03-01",
        repo_root=tmp_path,
    )
    manifest = verify_release(manifest_path.parent)
    assert manifest["row_counts"]["opinions"] == 2
    assert load_latest_manifest(tmp_path)["release_id"] == "2024-03-01"
    with pytest.raises(FileExistsError):
        create_release(
            opinions,
            output_root=tmp_path,
            release_id="2024-03-01",
        )


def test_temporal_research_blocks_future_law():
    as_of = parse_as_of_date("What was the law as of 2020-01-01?")
    assert as_of == date(2020, 1, 1)
    results = [{"year": 2019}, {"year": 2021}, {"name": "undated"}]
    filtered = filter_as_of(results, as_of)
    assert len(filtered) == 2
    assert temporal_leakage_rate(results, as_of) == pytest.approx(1 / 3)


def test_topic_labeler_has_offline_rules():
    labels = auto_label_topic(
        "The landlord filed an eviction action after the tenant breached the lease."
    )
    assert "Landlord-Tenant" in labels
    frame = batch_label_opinions(
        pd.DataFrame({"opinion_text": ["A breath test supported the DWI charge."]})
    )
    assert "DUI/DWI" in frame.iloc[0]["auto_topics"]


def test_transcript_index_search_and_timestamp(tmp_path):
    payload = {
        "case_number": "2024-0001",
        "case_name": "State v. Example",
        "argument_date": "2024-03-04",
        "vimeo_url": "https://vimeo.com/123",
        "segments": [
            {
                "start": 61.2,
                "end": 70.0,
                "display_speaker": "Justice",
                "text": "What standard of review should the court apply?",
            }
        ],
    }
    (tmp_path / "2024-0001.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    index = build_transcript_index(tmp_path)
    results = search_transcripts("standard of review", index)
    assert len(results) == 1
    assert results.iloc[0]["timestamp_url"].endswith("?t=61s")
    assert timestamp_url("https://example.test?a=1", 12.8).endswith("&t=12s")


def test_calendar_parser_and_business_days():
    html = """
    <table><tr><th>Date</th><th>Docket</th><th>Case</th><th>Time</th></tr>
    <tr><td>August 10, 2026</td><td>2026-0001</td>
    <td>State v. Example</td><td>9:30 AM</td></tr></table>
    """
    frame = parse_oral_argument_schedule(html)
    assert frame.iloc[0]["docket"] == "2026-0001"
    assert compute_filing_deadline(
        date(2026, 8, 7), 1, business_days=True
    ) == date(2026, 8, 10)


def test_readability_and_dataframe_scores():
    text = (
        "The court reviews the legal question independently. "
        "The parties agree that the record is complete. "
        "The judgment is therefore affirmed. "
    ) * 12
    scores = compute_readability(text)
    assert scores["word_count"] > 20
    frame = add_readability_scores(
        pd.DataFrame({"opinion_text": [text]})
    )
    assert "fog_index" in frame.columns


def test_glossary_and_bar_exam_tags():
    assert get_definition("de novo").startswith("Fresh review")
    assert find_terms("The court reviews the question de novo.")
    tags = tag_bar_exam_relevance(
        "The warrantless search raised a suppression issue.",
        ["criminal_procedure"],
    )
    assert tags[0]["subject"] == "Criminal Procedure"
    markup = annotate_terms_html("The court reviewed the issue de novo.")
    assert '<abbr class="legal-term"' in markup
    assert "Fresh review" in markup


def test_opinion_key_passages_preserve_offsets():
    text = (
        "Background facts were disputed by the parties. "
        "We hold that the warrant was required before this search. "
        "The dissenting justice would apply State v. Example, 180 N.H. 10."
    )
    passages = extract_key_passages(
        text, summary="The court held that a warrant was required."
    )
    kinds = {item["kind"] for item in passages}
    assert {"Holding", "Dissent", "Cited authority"} <= kinds
    for item in passages:
        assert text[item["start"] : item["end"]] == item["passage"]


def test_roadmap_analytics():
    opinions = pd.DataFrame(
        [
            {
                "case_number": "2024-1",
                "docket_numbers": ["2024-1"],
                "outcome": "reversed",
                "topics": ["criminal"],
                "author_display": "Justice A",
                "term_year": 2024,
                "date_argued": "2024-01-01",
                "date_issued": "2024-02-01",
            },
            {
                "case_number": "2024-2",
                "docket_numbers": ["2024-2"],
                "outcome": "affirmed",
                "topics": ["civil"],
                "author_display": "Justice B",
                "term_year": 2024,
                "date_argued": "2024-03-01",
                "date_issued": "2024-04-01",
            },
        ]
    )
    counsel = attorney_win_rates(
        opinions,
        [
            {
                "docket": "2024-1",
                "attorney_raw": "A. Lawyer",
                "side": "appellant",
            }
        ],
    )
    assert counsel.iloc[0]["won"] == 1
    assert disposition_trends(opinions).iloc[0]["mean"] == pytest.approx(0.5)
    timeline = build_case_timeline("2024-1", opinions)
    assert set(timeline["event_type"]) == {"Argument", "Opinion"}


def test_justice_topic_vote_rows():
    frame = justice_topic_voting(
        [
            {
                "outcome": "reversed",
                "topics": ["criminal"],
                "votes": {
                    "justice_a": {
                        "display_name": "Justice A",
                        "vote": "majority",
                    },
                    "justice_b": {
                        "display_name": "Justice B",
                        "vote": "not_participating",
                    },
                },
            }
        ]
    )
    assert len(frame) == 1
    assert frame.iloc[0]["pro_appellant"] == 1


def test_privacy_telemetry_drops_sensitive_text(tmp_path):
    clean = sanitize_properties(
        {"query_text": "sensitive", "result_count": 0, "page": "search"}
    )
    assert "query_text" not in clean
    event = record_event(
        "zero_result_search",
        {"query": "secret", "result_count": 0},
        path=tmp_path / "events.jsonl",
    )
    assert event["properties"] == {"result_count": 0}
    with pytest.raises(ValueError):
        record_event("raw_query", {})


def test_digest_recipient_configuration_is_deduplicated():
    assert configured_recipients(
        "one@example.test, two@example.test;one@example.test"
    ) == ["one@example.test", "two@example.test"]


def test_evaluation_gate_and_gold_categories():
    passing = gate_release(
        {
            "citation_precision": 0.99,
            "answer_coverage": 0.90,
            "unsupported_claim_rate": 0.01,
            "temporal_leakage_rate": 0.0,
        }
    )
    assert passing.passed
    failing = gate_release({"unsupported_claim_rate": 0.2})
    assert not failing.passed
    rows = [
        {"category": category}
        for category in (
            "pinpoint",
            "negative_premise",
            "conflicting_authorities",
            "no_answer_in_corpus",
            "temporal",
            "treatment",
            "holding_span",
            "speaker_attribution",
            "counsel_identity",
        )
    ]
    assert validate_gold_set(rows) == []
