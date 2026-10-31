import pandas as pd
import pytest
from fastapi import HTTPException

from webapp.backend import main


def test_argument_static_routes_take_precedence_over_case_numbers():
    from starlette.routing import Match
    def match(path):
        scope = {"type":"http", "path":path, "root_path":"", "method":"GET"}
        return next(route.endpoint.__name__ for route in main.app.routes if route.matches(scope)[0] is Match.FULL)
    assert match("/api/arguments/people") == "oral_argument_people"
    assert match("/api/arguments/people.csv") == "oral_argument_people_csv"
    assert match("/api/arguments/profile") == "oral_argument_profile"
    assert match("/api/arguments/2024-0001") == "argument_detail"


def test_people_advanced_visualizations(monkeypatch):
    monkeypatch.setattr(main, "oral_argument_people", lambda: {
        "attorneys": [{"attorney_name":"Alice", "firm":"Firm", "total_arguments":3, "total_duration_hours":1.5, "average_duration_minutes":30}],
        "firms": [{"firm_name":"Firm", "attorneys":["Alice"], "total_arguments":3, "unique_attorneys":1, "total_duration_hours":1.5}],
    })
    charts = main.oral_argument_people_visualizations()["charts"]
    assert charts["hierarchy"]["data"][0]["type"] == "sunburst"
    assert charts["scatter"]["data"][0]["type"] == "scatter"
    assert charts["treemap"]["data"][0]["type"] == "treemap"
    monkeypatch.setattr(main, "oral_argument_people", lambda: {"attorneys":[], "firms":[]})
    assert main.oral_argument_people_visualizations()["charts"] == {}


def test_attorney_justice_interaction_views(monkeypatch):
    from utils import data_loader
    data = {"summary":{"total_arguments_analyzed":2,"unique_attorneys":1,"unique_justices":1},
            "attorney_interactions":[{"attorney_name":"Alice", "interactions":[{"justice":"Justice A", "arguments":2}]}],
            "justice_interactions":[{"justice":"Justice A", "total_arguments":2, "unique_attorneys":1, "top_attorneys":[{"attorney":"Alice", "arguments":2}]}]}
    monkeypatch.setattr(data_loader, "load_attorney_justice_interactions", lambda: data)
    result = main.oral_argument_interactions(justice="Justice A")
    assert result["selected"]["total_arguments"] == 2
    assert set(result["charts"]) == {"attorneys", "workload", "unique", "heatmap"}
    assert result["charts"]["heatmap"]["data"][0]["type"] == "heatmap"
    monkeypatch.setattr(data_loader, "load_attorney_justice_interactions", lambda: {})
    assert not main.oral_argument_interactions(justice="")["available"]


def test_static_api_routes_are_not_shadowed_by_earlier_routes():
    from starlette.routing import Match
    routes = main.app.routes
    for index, route in enumerate(routes):
        path = getattr(route, "path", "")
        if not path.startswith("/api/") or "{" in path:
            continue
        for method in getattr(route, "methods", set()):
            scope = {"type":"http", "path":path, "root_path":"", "method":method}
            for earlier in routes[:index]:
                assert earlier.matches(scope)[0] is not Match.FULL, (
                    f"{method} {path} is shadowed by {getattr(earlier, 'path', earlier)}"
                )


def test_about_reports_roster_and_year_range(monkeypatch):
    monkeypatch.setattr(main, "opinions", lambda: pd.DataFrame({"term_year": [2021, 2024, None]}))
    monkeypatch.setattr(main, "_justices_metadata", lambda: {"a": {"key": "a", "is_active": True}})
    monkeypatch.setattr(main, "opinion_filters", lambda: {"updated": "test"})
    result = main.about()
    assert result == {"justices": [{"key": "a", "is_active": True}], "total": 3,
                      "year_min": 2021, "year_max": 2024, "updated": "test"}


def test_oral_statistics_charts_use_confirmed_dates(monkeypatch):
    from utils import data_loader
    rows = [
        {"argument_date": "2024-03-15", "date_is_estimated": False, "duration_seconds": 1800, "word_count": 2000},
        {"argument_date": "2024-10-01", "date_is_estimated": True, "duration_seconds": 2400, "word_count": 3000},
    ]
    monkeypatch.setattr(main, "argument_records", lambda: rows)
    monkeypatch.setattr(data_loader, "load_speaker_statistics", lambda: [])
    from utils import oral_arguments
    monkeypatch.setattr(oral_arguments, "has_confirmed_argument_date", lambda row: not row["date_is_estimated"])
    data = main.arguments_statistics()
    assert set(data["charts"]) == {"year", "month", "duration", "words"}
    import base64
    import numpy as np
    counts = data["charts"]["year"]["data"][0]["y"]
    assert np.frombuffer(base64.b64decode(counts["bdata"]), dtype=counts["dtype"]).tolist() == [1]
    assert data["speaker_summary"] is None


def test_oral_trends_include_complexity_and_case_types(monkeypatch):
    from utils import data_loader
    monkeypatch.setattr(data_loader, "load_enhanced_statistics", lambda: {
        "temporal_trends": {"yearly": {"2024": {"total_arguments": 2, "avg_duration_min": 30, "median_duration_min": 30}}},
        "complexity_analysis": {name: {"count": 1, "min_duration": 10, "avg_duration": 20, "max_duration": 30, "avg_segments": 100} for name in ["Simple", "Moderate", "Complex", "Very Complex"]},
        "case_parties": {"case_types": {"Civil": 2}},
        "attorney_networks": {"solo_practitioners": ["A"]},
    })
    data = main.arguments_trends()
    assert data["available"] and data["solo_count"] == 1
    assert {"yearly", "yearly_duration", "complexity", "complexity_duration", "case_types"} <= set(data["charts"])
    assert data["complexity"]["Simple"]["count"] == 1


def test_opinion_filters_and_literal_search(monkeypatch):
    df = pd.DataFrame([
        {"case_number": "2024-1", "case_name": "Alpha v. State", "rsa_citations": "RSA 123", "term_year": 2024, "outcome": "affirmed", "author": "hicks", "date_issued": "2024-02-01", "is_unanimous": True, "has_dissent": False, "has_separate_concurrence": False},
        {"case_number": "2023-2", "case_name": "Beta", "rsa_citations": "", "term_year": 2023, "outcome": "reversed", "author": "lynn", "date_issued": "2023-01-01", "is_unanimous": False, "has_dissent": True, "has_separate_concurrence": False},
    ])
    monkeypatch.setattr(main, "opinions", lambda: df)
    def search(**overrides):
        params = dict(year=[], outcome=[], author=[], decision="all", q="", table_q="", sort_by="date_issued", sort_direction="desc", offset=0, limit=100)
        params.update(overrides)
        return main.list_opinions(**params)

    assert search(year=[2024], q="RSA 123")["count"] == 1
    assert search(q=".*")["count"] == 0
    assert search(decision="dissent")["items"][0]["case_number"] == "2023-2"
    assert [row["case_number"] for row in search(sort_by="case_name", sort_direction="asc")["items"]] == ["2024-1", "2023-2"]
    assert [row["case_number"] for row in search(sort_by="case_name", sort_direction="desc")["items"]] == ["2023-2", "2024-1"]
    csv = main.download_opinions(year=[2024], outcome=[], author=[], decision="all", q="")
    assert "2024-1" in csv.body.decode() and "2023-2" not in csv.body.decode()
    with pytest.raises(HTTPException) as missing:
        main.get_opinion("missing")
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as invalid:
        main.get_opinion("invalid.txt")
    assert invalid.value.status_code == 400


def test_dashboard_uses_opinion_data(monkeypatch):
    df = pd.DataFrame([
        {"date_issued": "2024-03-14", "term_year": 2024, "topics": "['evidence', 'criminal_law']", "is_unanimous": True, "has_dissent": False},
        {"date_issued": "2023-03-14", "term_year": 2023, "topics": "['evidence']", "is_unanimous": False, "has_dissent": True},
    ])
    monkeypatch.setattr(main, "opinions", lambda: df)
    monkeypatch.setattr(main, "opinion_filters", lambda: {"updated": "test"})
    class FixedDate:
        @staticmethod
        def today():
            from datetime import date
            return date(2026, 3, 14)
    monkeypatch.setattr(main, "date", FixedDate)
    result = main.dashboard()
    assert result["history_exact"] is True
    assert len(result["history"]) == 2
    assert result["topics"][0] == {"name": "evidence", "count": 2}
    assert (result["total"], result["term_opinions"], result["unanimous_rate"], result["dissent_count"]) == (2, 1, 50, 1)


def test_search_respects_as_of_date(monkeypatch):
    class Retriever:
        _nh_vectorizer = object()
        _nh_matrix = object()
        def retrieve_cases(self, query, source, top_k):
            return [{"name": "Old", "year": 2020}, {"name": "New", "year": 2025}]
    monkeypatch.setattr(main, "_retriever", lambda: Retriever())
    result = main.research_search(main.ResearchRequest(query="cases as of 2022", limit=3))
    assert [item["name"] for item in result["results"]] == ["Old"]


def test_referential_search_expands_query_and_keeps_previous_cases(monkeypatch):
    class Retriever:
        _nh_vectorizer = object()
        _nh_matrix = object()
        query = ""
        def retrieve_cases(self, query, source, top_k):
            self.query = query
            return [{"name":"New", "source":"nh-supreme-court", "href":"new", "score":0.8}]
    retriever = Retriever()
    monkeypatch.setattr(main, "_retriever", lambda: retriever)
    request = main.ResearchRequest(
        query="What did the dissent say in that case?",
        previous_query="Explain the holding in Old v. State",
        previous_cases=[{"name":"Old", "source":"nh-supreme-court", "href":"old", "score":0.9}],
    )
    result = main.research_search(request)
    assert "Previous topic: Explain the holding in Old v. State" in retriever.query
    assert "Cases: Old" in retriever.query
    assert [item["name"] for item in result["results"]] == ["Old", "New"]


def test_search_prewarm_reports_success_and_failure(monkeypatch):
    class Retriever:
        _nh_vectorizer = None
        _nh_matrix = None
        calls = 0
        def _build_nh_index(self):
            self.calls += 1
            self._nh_vectorizer = object()
            self._nh_matrix = object()
    retriever = Retriever()
    monkeypatch.setattr(main, "_retriever", lambda: retriever)
    monkeypatch.setattr(main, "_search_status", "not_started")
    main._warm_search_index()
    assert main.research_status() == {"status": "ready"}
    main._warm_search_index()
    assert retriever.calls == 1
    retriever._nh_vectorizer = None
    monkeypatch.setattr(retriever, "_build_nh_index", lambda: None)
    main._warm_search_index()
    assert main.research_status() == {"status": "unavailable"}


def test_search_index_reads_only_texts_for_opinions(tmp_path, monkeypatch):
    from pathlib import Path
    from utils import chat_retriever
    processed = tmp_path / "processed"
    text_dir = processed / "text"
    text_dir.mkdir(parents=True)
    pd.DataFrame([
        {"case_number":"case-a", "case_name":"Alpha State", "summary_paragraph":"common evidence"},
        {"case_number":"case-b", "case_name":"Beta State", "summary_paragraph":"common evidence"},
    ]).to_csv(processed / "opinions.csv", index=False)
    for name in ("case-a", "case-b", "unrelated"):
        (text_dir / f"{name}.txt").write_text("common evidence argument", encoding="utf-8")
    monkeypatch.setattr(chat_retriever, "data_root", lambda: tmp_path)
    original_read = Path.read_text
    read_names = []
    def tracked_read(path, *args, **kwargs):
        if path.parent == text_dir:
            read_names.append(path.name)
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", tracked_read)
    retriever = chat_retriever.CaseRetriever()
    retriever._build_nh_index()
    assert retriever._nh_matrix is not None
    assert set(read_names) == {"case-a.txt", "case-b.txt"}


def test_ai_answers_are_verified_against_retrieved_sources(monkeypatch):
    from utils import chat_provider, claim_verifier
    from utils.claim_verifier import VerificationResult

    captured = {}
    monkeypatch.setattr(main, "_research_results", lambda request, use_hybrid=False: ([{"name": "Old", "year": 2020, "source": "nh-supreme-court", "href":"old"}], None))
    monkeypatch.setattr(chat_provider, "generate_chat_response", lambda **kwargs: captured.update(kwargs) or "Unsupported generated claim.")
    monkeypatch.setattr(claim_verifier, "verify_answer", lambda answer, sources: VerificationResult(
        publishable_text="No supported answer", verified_claims=(), unsupported_claims=(answer,), answer_coverage=0.0, unsupported_claim_rate=1.0))
    result = main.research_answer(main.ResearchRequest(query="test research question", limit=3, previous_answer="Earlier supported answer"))
    assert result["answer"] == "No supported answer"
    assert result["unsupported_removed"] == 1
    assert captured["conversation_history"] == [{"role":"assistant", "content":"Earlier supported answer"}]


def test_ai_answer_links_cited_retrieved_cases(monkeypatch):
    from utils import chat_provider, claim_verifier
    from utils.claim_verifier import VerificationResult

    cases = [{"name":"Old v. State", "source":"nh-supreme-court", "docket_number":"2024-0001", "url":"/case-explorer?case=2024-0001"}]
    monkeypatch.setattr(main, "_research_results", lambda request, use_hybrid=False: (cases, None))
    monkeypatch.setattr(chat_provider, "generate_chat_response", lambda **kwargs: "*Old v. State* held this.")
    monkeypatch.setattr(claim_verifier, "verify_answer", lambda answer, sources: VerificationResult(
        publishable_text=answer, verified_claims=(), unsupported_claims=(), answer_coverage=1.0, unsupported_claim_rate=0.0))
    result = main.research_answer(main.ResearchRequest(query="Explain the case holding"))
    assert result["answer"] == "[*Old v. State*](/case-explorer?case=2024-0001) held this."


def test_case_detail_joins_votes_counsel_arguments_and_citations(monkeypatch):
    row = {"case_number": "2024-0001", "case_name": "Example", "date_issued": "2024-01-01", "date_argued": None, "topics": "['evidence']", "rsa_citations": "['RSA 123']", "outcome": "affirmed"}
    monkeypatch.setattr(main, "get_opinion", lambda _: {"opinion": row, "text": "The opinion text."})
    monkeypatch.setattr(main, "opinions", lambda: pd.DataFrame([row, {"case_number": "2023-0002", "case_name": "Earlier"}]))
    files = {
        "all_opinions.json": [{"case_number": "2024-0001", "votes": {"donovan": {"vote": "majority", "display_name": "Donovan, J."}}}],
        "brief_counsel.json": {"facts": [{"docket": "2024-0001", "attorney_raw": "Counsel"}]},
        "oral_arguments.json": [{"case_number": "2024-0001", "vimeo_url": "https://vimeo.com/1"}],
        "oral_arguments_attorney_stats.json": {"case_attorneys": {"2024-0001": [{"name": "Counsel"}]}},
        "citations.json": {"2024-0001": {"cites": ["2023-0002"]}},
        "cited_by.json": {},
    }
    monkeypatch.setattr(main, "_optional_json", lambda name, default: files.get(name, default))
    result = main.case_detail("2024-0001")
    assert result["votes"]["donovan"]["vote"] == "majority"
    assert result["counsel"][0]["attorney_raw"] == "Counsel"
    assert result["argument"]["case_number"] == "2024-0001" and result["roster"][0]["name"] == "Counsel"
    assert result["cites"] == [{"case_number": "2023-0002", "case_name": "Earlier", "citation": "2023-0002"}]
    assert result["bench_chart"]["data"][0]["type"] == "scatter"
    assert result["topics"] == ["evidence"] and result["statutes"] == ["RSA 123"]


def test_case_detail_extracts_streamlit_style_appearance_counsel(monkeypatch):
    row = {"case_number": "2024-0002", "case_name": "Example", "date_issued": "2024-01-01", "topics": "[]", "rsa_citations": "[]"}
    text = "\n".join([
        "Opinion Issued: January 1, 2024",
        "A. Counsel, assistant attorney general (Robert L. Baldridge, assistant attorney general, on the brief and orally), for the State.",
        "B. Counsel, for the defendant.",
        "",
        "GOULD, J.",
        "I. Background",
        "The opinion body.",
    ])
    monkeypatch.setattr(main, "get_opinion", lambda _: {"opinion": row, "text": text})
    monkeypatch.setattr(main, "opinions", lambda: pd.DataFrame([row]))
    monkeypatch.setattr(main, "_optional_json", lambda _name, default: default)

    result = main.case_detail("2024-0002")

    assert result["appearance_rows"] == [{"side": "State", "participants": ["Robert L. Baldridge"]}]
    assert "GOULD, J." not in result["appearance"]


def test_argument_search_filters_and_reader_support_combined_dockets(monkeypatch):
    rows = [
        {"case_number": "2024-0001_2024-0002", "case_name": "State v. Example", "argument_date": "2024-03-01", "term_year": 2024, "duration_seconds": 1200, "segment_count": 100, "transcript_text": "A warrantless search"},
        {"case_number": "2023-0003", "case_name": "A v. B", "argument_date": "2023-04-01", "term_year": 2023, "duration_seconds": 2400, "segment_count": 120, "transcript_text": "Civil dispute"},
    ]
    monkeypatch.setattr(main, "argument_records", lambda: rows)
    monkeypatch.setattr(main, "_optional_json", lambda name, default: default)
    results = main.list_arguments(q="warrantless", date=[], year_min=2000, year_max=2026, duration_min=0, duration_max=100, segments_min=0, segments_max=200, case_type="criminal", limit=24)
    assert results["count"] == 1 and results["items"][0]["case_number"] == "2024-0001_2024-0002"
    assert "transcript_text" not in results["items"][0]
    assert main.argument_detail("2024-0001_2024-0002")["record"]["case_number"] == "2024-0001_2024-0002"
    assert main.argument_detail("2024-0002")["record"]["case_number"] == "2024-0001_2024-0002"
    assert main.arguments_overview()["statistics"]["argument_count"] == 2


def test_topics_filter_rsa_and_classify_like_streamlit(monkeypatch):
    rows = [
        {"case_number": "one", "case_name": "One", "term_year": 2024, "case_type": "criminal", "topics": "['evidence']", "rsa_citations": "['RSA 265-A:39']", "outcome": "affirmed"},
        {"case_number": "two", "case_name": "Two", "term_year": 2023, "case_type": "", "topics": "['family_law']", "rsa_citations": "['RSA 458']", "outcome": "reversed"},
        {"case_number": "three", "case_name": "Three", "term_year": 2010, "case_type": "civil", "topics": "['evidence']", "rsa_citations": "[]", "outcome": "affirmed"},
    ]
    monkeypatch.setattr(main, "opinions", lambda: pd.DataFrame(rows))
    monkeypatch.setattr(main, "opinion_filters", lambda: {"updated": "test"})
    monkeypatch.setattr(main, "_topic_profile", lambda key, label: {"label": label})
    result = main.topics_page(year_min=2020, year_max=2025, topic=["evidence"], rsa="265-A")
    assert result["selected"]["count"] == 1
    assert result["rsa"]["items"][0]["case_number"] == "one"
    assert result["groups"]["criminal"]["count"] == 1
    assert result["groups"]["family/domestic"]["count"] == 1
    assert result["groups"]["civil"]["count"] == 0
    assert result["charts"]["topics"]["data"][0]["orientation"] == "h"
    assert result["charts"]["outcomes"]["data"][0]["type"] == "pie"
    assert result["charts"]["trend"]["data"][0]["mode"] == "lines+markers"
    assert result["charts"]["rsa"]["data"][0]["type"] == "bar"
    assert result["groups"]["criminal"]["charts"]["outcomes"]["data"][0]["type"] == "pie"
    assert result["groups"]["civil"]["charts"] == {}


def test_topic_disposition_profile_and_export(monkeypatch):
    from utils import data_loader
    matches = pd.DataFrame([
        {"argument_id":"a", "case_name":"Alpha", "argument_date":"2024-01-01", "term_year":2024, "resolution_type":"opinion", "disposition_date":"2024-02-01", "days_to_disposition":31, "outcome":"affirmed", "case_type":"criminal", "lower_court":"Superior", "author":"Judge"},
        {"argument_id":"b", "case_name":"Beta", "argument_date":"2023-01-01", "term_year":2023, "resolution_type":"unmatched", "disposition_date":None, "days_to_disposition":None, "outcome":None, "case_type":"civil", "lower_court":"Superior", "author":None},
        {"argument_id":"c", "case_name":"Other", "argument_date":"2022-01-01", "term_year":2022, "resolution_type":"opinion", "disposition_date":"2022-02-01", "days_to_disposition":31, "outcome":"reversed", "case_type":"civil", "lower_court":"Superior", "author":"Judge"},
    ])
    monkeypatch.setattr(data_loader, "load_argument_dispositions", lambda: matches)
    monkeypatch.setattr(data_loader, "load_argument_topics", lambda: pd.DataFrame([{"argument_id":"a", "topic":"Evidence"}, {"argument_id":"b", "topic":"Evidence"}]))
    monkeypatch.setattr(data_loader, "load_argument_participants", lambda: pd.DataFrame([{"argument_id":"a", "attorney_name":"Counsel", "firm":"Firm"}]))
    profile = main._topic_profile("evidence", "Evidence")
    assert (profile["arguments"], profile["resolved"], profile["median_days"]) == (2, 1, 31)
    assert {"resolution", "yearly", "timing", "timing_type", "case_types", "attorneys", "firms", "outcomes"} == set(profile["charts"])
    assert profile["outcomes"] == [{"Outcome":"affirmed", "Count":1}]
    csv = main.download_topic_dispositions("evidence").body.decode()
    assert "Alpha" in csv and "Beta" in csv and "Other" not in csv
    assert main._topic_profile("missing", "Missing") is None


def test_orders_filter_sort_and_export(monkeypatch):
    frame = pd.DataFrame([
        {"case_number": "2024-1", "case_name": "State v. Alpha", "term_year": 2024, "date_issued": "2024-03-01", "case_type": "criminal", "order_source": "case_order"},
        {"case_number": "2024-2", "case_name": "State v. Beta", "term_year": 2024, "date_issued": None, "case_type": "criminal", "order_source": "3jx_order"},
        {"case_number": "2023-3", "case_name": "Gamma", "term_year": 2023, "date_issued": "2023-02-01", "case_type": "civil", "order_source": "case_order"},
    ])
    monkeypatch.setattr(main, "orders", lambda: frame)
    result = main.list_orders(year=[2024], case_type=["criminal"], source=[], q="state", offset=0, limit=100)
    assert result["count"] == 2
    assert [row["case_number"] for row in result["items"]] == ["2024-1", "2024-2"]
    assert result["charts"]["types"]["data"][0]["type"] == "bar"
    assert result["charts"]["years"]["data"][0]["mode"] == "lines+markers"
    paged = main.list_orders(year=[2024], case_type=["criminal"], source=[], q="state", offset=1, limit=1)
    assert paged["charts"] == result["charts"]
    empty = main.list_orders(year=[], case_type=[], source=[], q=".*", offset=0, limit=100)
    assert empty["count"] == 0 and empty["charts"] == {}
    csv = main.download_orders(year=[2024], case_type=[], source=["3jx_order"], q="").body.decode()
    assert "2024-2" in csv and "2024-1" not in csv


def test_trial_court_breakdown_rates_and_csv(monkeypatch):
    frame = pd.DataFrame([
        {"case_number": "1", "term_year": 2024, "lower_court": "Superior Court (Smith, J.)", "outcome": "affirmed"},
        {"case_number": "2", "term_year": 2024, "lower_court": "Superior Court (Smith, J.)", "outcome": "reversed_and_remanded"},
        {"case_number": "3", "term_year": 2023, "lower_court": "Circuit Court - Family Division (Jones, J.)", "outcome": "affirmed"},
    ])
    monkeypatch.setattr(main, "opinions", lambda: frame)
    monkeypatch.setattr(main, "opinion_filters", lambda: {"updated": "test"})
    result = main.trial_courts(year=[2024], min_cases=2)
    assert (result["total"], result["affirmed"], result["reversed"], result["affirm_rate"]) == (2, 1, 1, 50.0)
    assert result["judges"][0]["judge"] == "Smith"
    assert result["judges"][0]["Affirm %"] == 50 and result["judges"][0]["Reversal %"] == 50
    assert result["court_types"][0]["court_type"] == "Superior Court"
    assert result["charts"]["court_types"]["data"][0]["orientation"] == "v"
    assert result["charts"]["judges"]["data"][0]["orientation"] == "h"
    assert {trace["name"] for trace in result["charts"]["judges"]["data"]} == {"Affirmed", "Reversed & Remanded"}
    assert main.trial_courts(year=[2024], min_cases=3)["charts"]["judges"] is None
    csv = main.download_trial_courts(year=[2023]).body.decode()
    assert "Jones" in csv and "Smith" not in csv


def test_justice_profile_excludes_preappointment_cases_and_builds_agreement(monkeypatch):
    monkeypatch.setattr(main, "_justices_metadata", lambda: {"macdonald": {"key": "macdonald", "is_active": True, "date_appointed": "2020-06-01"}})
    monkeypatch.setattr(main, "opinions", lambda: pd.DataFrame([
        {"term_year": 2020, "date_issued": "2020-02-01", "author": "macdonald"},
        {"term_year": 2020, "date_issued": "2020-08-01", "author": "macdonald"},
    ]))
    raw = [
        {"case_number": "old", "term_year": 2020, "date_issued": "2020-02-01", "votes": {"macdonald": {"vote": "majority"}, "donovan": {"vote": "majority"}}},
        {"case_number": "new", "term_year": 2020, "date_issued": "2020-08-01", "votes": {"macdonald": {"vote": "dissent"}, "donovan": {"vote": "majority"}}},
    ]
    monkeypatch.setattr(main, "_optional_json", lambda filename, default: raw)
    result = main.justice_page(justice="macdonald", year_min=2020, year_max=2020)
    assert result["authored"] == 1 and result["participated"] == 1 and result["dissents"] == 1
    assert [row["case_number"] for row in result["cases"]] == ["new"]
    a, b = main.JUSTICE_KEYS.index("macdonald"), main.JUSTICE_KEYS.index("donovan")
    assert result["matrix"][a][b] == 0.5
    assert result["charts"]["votes"]["data"][0]["type"] == "pie"
    assert result["charts"]["agreement"]["data"][0]["type"] == "heatmap"
    assert result["charts"]["authored_year"]["data"][0]["type"] == "bar"
    assert result["charts"]["authorship"]["data"][0]["type"] == "bar"


def test_analysis_uses_filtered_opinions_and_original_plotly_charts(monkeypatch):
    rows = [
        {"case_number": "2024-0001", "case_name": "One", "term_year": 2024, "date_issued": "2024-01-01", "author": "donovan", "case_type": "criminal", "appeal_type": "direct", "lower_court_type": "superior", "outcome": "affirmed", "is_unanimous": True, "has_dissent": False, "days_to_decision": 10, "word_count": 1000, "topics": "['criminal']", "rsa_citations": "['RSA 123:1']", "standard_of_review": "[]", "involves_statutory_interpretation": True},
        {"case_number": "2023-0002", "case_name": "Two", "term_year": 2023, "date_issued": "2023-01-01", "author": "donovan", "case_type": "civil", "appeal_type": "direct", "lower_court_type": "superior", "outcome": "reversed", "is_unanimous": False, "has_dissent": True, "days_to_decision": 20, "word_count": 1200, "topics": "['evidence']", "rsa_citations": "[]", "standard_of_review": "[]", "involves_statutory_interpretation": False},
    ]
    monkeypatch.setattr(main, "opinions", lambda: pd.DataFrame(rows))
    monkeypatch.setattr(main, "opinion_filters", lambda: {"updated": "test"})
    result = main.analysis_page(year_min=2024, year_max=2024, rsa="123")
    assert (result["total"], result["unanimous"], result["dissents"], result["avg_days"]) == (1, 1, 0, 10)
    assert result["rsa_cases"][0]["case_number"] == "2024-0001"
    assert result["charts"]["outcomes"]["layout"]["title"]["text"] == "Outcomes"


def test_advanced_analysis_and_csv_use_selected_dispositions(monkeypatch):
    from utils import data_loader
    rows = [
        {"argument_id": "one", "case_name": "One", "argument_date": "2024-01-01", "term_year": 2024, "resolution_type": "opinion", "disposition_date": "2024-02-01", "days_to_disposition": 31, "author": "donovan", "is_unanimous": True, "has_dissent": False, "case_type": "criminal", "lower_court": "Superior Court", "outcome": "affirmed", "vote_string": "5-0"},
        {"argument_id": "two", "case_name": "Two", "argument_date": "2024-01-01", "term_year": 2024, "resolution_type": "3jx_order", "disposition_date": "2024-01-15", "days_to_disposition": 14, "author": None, "is_unanimous": None, "has_dissent": None, "case_type": "criminal", "lower_court": "Superior Court", "outcome": "affirmed", "vote_string": None},
        {"argument_id": "old", "case_name": "Old", "argument_date": "2020-01-01", "term_year": 2020, "resolution_type": "opinion", "disposition_date": "2020-01-30", "days_to_disposition": 29, "author": "donovan", "is_unanimous": True, "has_dissent": False, "case_type": "civil", "lower_court": "Superior Court", "outcome": "affirmed", "vote_string": "5-0"},
    ]
    monkeypatch.setattr(data_loader, "load_argument_dispositions", lambda: pd.DataFrame(rows))
    monkeypatch.setattr(data_loader, "load_argument_topics", lambda: pd.DataFrame())
    result = main.advanced_analysis(year_min=2024, year_max=2024)
    assert result["count"] == 2 and result["author_count"] == 1
    assert result["routing_counts"]["3jx_order"] == 1
    assert result["percentiles"]["0.5"] == 14
    assert result["charts"]["authors"]["layout"]["title"]["text"] == "Opinions Authored"
    export = main.advanced_analysis_csv(kind="authorship", year_min=2024, year_max=2024).body.decode()
    assert "One" in export and "Two" not in export and "Old" not in export


def test_argument_disposition_filters_respect_age_boundaries(monkeypatch):
    from utils import data_loader
    base = {"case_name":"Case", "argument_date":"2024-01-01", "term_year":2024, "resolution_type":"opinion", "disposition_date":"2024-03-01", "outcome":"affirmed", "case_type":"criminal", "author":"donovan", "is_unanimous":True, "has_dissent":False, "lower_court":"Superior", "duration_seconds":1800, "has_transcript":True, "is_combined_docket":False}
    frame = pd.DataFrame([{**base,"argument_id":f"case-{days}","case_number":f"case-{days}","days_to_disposition":days} for days in (90,91,180,181,365,366,None)])
    monkeypatch.setattr(data_loader, "load_argument_dispositions", lambda: frame)
    monkeypatch.setattr(data_loader, "load_argument_dispositions_metadata", lambda: {})
    result = main.analysis_arguments(year_min=2024,year_max=2024,resolution="",case_type="",outcome="",age="91-180")
    assert result["total"] == 2 and result["resolved"] == 2
    assert {row["days_to_disposition"] for row in result["fastest"]} == {91,180}
    pending = main.analysis_arguments(year_min=2024,year_max=2024,resolution="",case_type="",outcome="",age="pending")
    assert pending["total"] == 1 and not pending["percentiles"]
    export = main.analysis_arguments_csv(year_min=2024,year_max=2024,resolution="",case_type="",outcome="",age="365+").body.decode()
    assert "case-366" in export and "case-365," not in export


def test_legal_authority_and_issue_threads_respect_research_date(monkeypatch):
    from datetime import date
    from utils import authority_graph, case_recommender
    from utils.authority_graph import Treatment
    rows = [{"case_number":f"202{i}-0001", "case_name":f"Case {i}", "date_issued":f"202{i}-01-01", "term_year":2020+i, "topics":"['criminal']", "summary_paragraph":f"Rule {i}", "outcome":"affirmed", "has_dissent":False} for i in range(4)]
    monkeypatch.setattr(main, "opinions", lambda: pd.DataFrame(rows))
    treatment = Treatment("2023-0001","2020-0001","followed",0.9,0,20,"The later opinion follows this rule.",date(2023,1,1))
    monkeypatch.setattr(authority_graph, "load_treatments", lambda path: [treatment])
    monkeypatch.setattr(case_recommender, "get_similar_cases", lambda *args,**kwargs: pd.DataFrame())
    monkeypatch.setattr(main, "_optional_json", lambda *args,**kwargs: {})
    earlier = main.legal_authority("2020-0001",date(2022,12,31))
    later = main.legal_authority("2020-0001",date(2023,1,1))
    assert earlier["treatments"] == [] and later["treatments"][0]["display_label"] == "followed"
    issues = main.legal_issues(date(2022,12,31))["issues"]
    assert len(issues[0]["states"]) == 3
    assert all(item["decided_on"] <= date(2022,12,31) for item in issues[0]["states"])


def test_workspace_exports_resolve_current_text_and_validate_offsets(monkeypatch):
    import json
    monkeypatch.setattr(main, "get_opinion", lambda case: {"opinion": {"case_name": "A < B", "citation": "123 N.H. 1", "pdf_url": "https://example.test/case"}, "text": "The holding is affirmed."})
    item = main.workspace_case_item("2024-0001")
    assert item["end"] == len("The holding is affirmed.")
    payload = main.WorkspacePayload(corpus_version="test", items=[item], notes=[{"text":"A < B & C", "created_at":"2026-01-01"}])
    exported = json.loads(main.export_research_workspace(payload,format="json").body)
    assert exported["items"][0]["source_span"] == "The holding is affirmed."
    assert main.export_research_workspace(payload,format="pdf").body.startswith(b"%PDF")
    assert "The holding is affirmed." in main.export_research_workspace(payload,format="markdown").body.decode()
    invalid = main.WorkspacePayload(corpus_version="test",items=[{**item,"start":10,"end":2}])
    with pytest.raises(HTTPException) as error:
        main.export_research_workspace(invalid,format="json")
    assert error.value.status_code == 422


def test_docket_media_viewer_date_and_safe_transcript_filter(monkeypatch):
    from datetime import date
    text = "We hold that the trial court properly applied the standard of review. " * 10
    row = {"case_number":"2024-0001", "case_name":"Example", "summary_paragraph":"We review the standard of review.", "topics":"['criminal']", "date_argued":"2024-01-01", "date_issued":"2024-02-01", "outcome":"affirmed"}
    monkeypatch.setattr(main, "get_opinion", lambda _: {"opinion":row, "text":text})
    monkeypatch.setattr(main, "opinions", lambda: pd.DataFrame([row]))
    monkeypatch.setattr(main, "orders", lambda: pd.DataFrame())
    monkeypatch.setattr(main, "_optional_json", lambda name, default: default)
    assert main.date_calculator(date(2024,1,5),1,True)["date"] == date(2024,1,8)
    viewer = main.legal_opinion_viewer("2024-0001")
    assert viewer["scores"]["word_count"] > 20 and viewer["highlights"]
    timeline = main.legal_case_timeline("2024-0001")
    assert {item["event_type"] for item in timeline["items"]} == {"Argument","Opinion"}
    with pytest.raises(HTTPException) as invalid:
        main.transcript_moments(q="test",case_number="../escape")
    assert invalid.value.status_code == 400


def test_predictive_analytics_passes_declared_features(monkeypatch):
    from utils import ml_predictor
    captured = {}
    def predict(details, opinions, model_path):
        captured.update(details)
        return ml_predictor.Prediction(0.6,0.4,"Affirmed",0.6,(("topic",0.2),),42,0.7)
    monkeypatch.setattr(ml_predictor,"predict_outcome",predict)
    monkeypatch.setattr(main,"opinions",lambda:pd.DataFrame())
    result = main.legal_predict(main.PredictionRequest(topic="criminal",appellant_type="Individual",lower_court_type="superior",year=2024,word_count=4000,criminal=True))
    assert result["probability_affirmed"] == 0.6 and result["training_rows"] == 42
    assert captured["is_criminal_appeal"] == 1 and captured["panel_size"] == 5


def test_attorney_analytics_uses_existing_win_rate_calculation(monkeypatch):
    data = pd.DataFrame([{"attorney":"Counsel", "docket":"2024-0001", "topic":"Criminal", "author":"Justice", "year":2024, "won":1},
                         {"attorney":"Counsel", "docket":"2023-0001", "topic":"Civil", "author":"Justice", "year":2023, "won":0}])
    monkeypatch.setattr(main,"_attorney_outcomes",lambda:data)
    assert main.legal_attorneys()["items"] == [{"name":"Counsel","count":2}]
    result = main.legal_attorney_detail("Counsel")
    assert result["total_cases"] == 2 and result["win_rate"] == 0.5 and result["unique_topics"] == 2


def test_review_requires_configured_token_and_preserves_provenance(monkeypatch,tmp_path):
    import sqlite3
    db = tmp_path / "reviews.sqlite"
    monkeypatch.setenv("NHSC_REVIEW_TOKEN","test-secret")
    monkeypatch.setenv("NHSC_REVIEW_DB",str(db))
    monkeypatch.setattr(main,"_quality_queue",lambda:pd.DataFrame([{"record_id":"2024-0001","field_name":"outcome","source_sha256":"abc","extractor_version":"v1"}]))
    request = main.ReviewRequest(record_id="2024-0001",field_name="outcome",source_sha256="abc",extractor_version="v1",reviewed_value='"affirmed"')
    with pytest.raises(HTTPException) as denied:
        main.save_legal_review(request,x_review_token="wrong")
    assert denied.value.status_code == 403 and not db.exists()
    assert main.save_legal_review(request,x_review_token="test-secret")["status"] == "saved"
    with sqlite3.connect(db) as connection:
        saved = connection.execute("SELECT record_id,field_name,source_sha256,extractor_version,reviewed_value_json FROM reviewed_observation").fetchone()
    assert saved == ("2024-0001","outcome","abc","v1",'"affirmed"')
    with pytest.raises(HTTPException) as unknown:
        main.save_legal_review(request.model_copy(update={"record_id":"other"}),x_review_token="test-secret")
    assert unknown.value.status_code == 404


def test_oral_attorney_profile_joins_cases_and_dispositions(monkeypatch):
    from utils import data_loader
    data = {"attorneys":[{"attorney_name":"Counsel", "total_arguments":1, "cases":["2024-0001"], "firm":"Firm"}],"firms":[{"firm_name":"Firm","attorneys":["Counsel"],"cases":["2024-0001"]}],"firm_metadata":{"Firm":{"full_name":"Firm LLP"}}}
    monkeypatch.setattr(main,"oral_argument_people",lambda:data)
    monkeypatch.setattr(main,"argument_records",lambda:[{"case_number":"2024-0001","case_name":"Example","argument_date":"2024-01-01","transcript_text":"private full text"}])
    monkeypatch.setattr(main,"_optional_json",lambda filename,default:{"case_attorneys":{"2024-0001":[{"name":"Counsel","firm":"Firm"},{"name":"Other","firm":"Other Firm"}]}})
    monkeypatch.setattr(data_loader,"load_argument_dispositions",lambda:pd.DataFrame([{"argument_id":"2024-0001","term_year":2024,"resolution_type":"opinion","days_to_disposition":30,"case_type":"civil","lower_court":"Superior","outcome":"affirmed"}]))
    monkeypatch.setattr(data_loader,"load_argument_participants",lambda:pd.DataFrame([{"argument_id":"2024-0001","attorney_name":"Counsel","firm":"Firm"}]))
    monkeypatch.setattr(data_loader,"load_argument_topics",lambda:pd.DataFrame([{"argument_id":"2024-0001","topic":"evidence"}]))
    attorney = main.oral_argument_profile(kind="attorney",name="Counsel")
    assert attorney["dispositions"]["resolved"] == 1 and attorney["dispositions"]["median"] == 30
    assert attorney["cases"][0]["case_name"] == "Example" and "transcript_text" not in attorney["cases"][0]
    firm = main.oral_argument_profile(kind="firm",name="Firm")
    assert firm["firm_info"]["full_name"] == "Firm LLP" and firm["members"][0]["attorney_name"] == "Counsel"
    assert firm["cases"][0]["firm_attorneys"] == "Counsel"
    assert firm["dispositions"]["roster"] == [{"attorney_name":"Counsel", "arguments":1, "share":"100.0%"}]
    assert firm["dispositions"]["yearly"] == [{"term_year":2024, "resolution_type":"opinion", "count":1}]
    assert firm["dispositions"]["percentiles"] == [30, 30, 30]


def test_person_disposition_export_and_cohort(monkeypatch):
    rows = pd.DataFrame([
        {"argument_id":"a", "case_name":"Alpha", "argument_date":"2024-01-01", "term_year":2024, "resolution_type":"opinion", "disposition_date":"2024-02-01", "days_to_disposition":31, "outcome":"affirmed", "case_type":"civil", "lower_court":"Superior", "author":"Judge"},
        {"argument_id":"b", "case_name":"Beta", "argument_date":"2023-01-01", "term_year":2023, "resolution_type":"unmatched", "disposition_date":None, "days_to_disposition":None, "outcome":None, "case_type":"criminal", "lower_court":"Superior", "author":None},
    ])
    participants = pd.DataFrame([{"argument_id":"a", "side":"appellant", "role":"counsel", "firm":"Firm", "source":"roster"}])
    monkeypatch.setattr(main, "_person_dispositions", lambda kind,name:(rows,participants,rows.iloc[:1]))
    csv = main.person_dispositions_csv(kind="attorney", name="Counsel").body.decode()
    assert "attorney_side" in csv and "appellant" in csv and "Alpha" in csv and "Beta" not in csv
    csv = main.person_dispositions_csv(kind="firm", name="Firm").body.decode()
    assert "attorney_side" not in csv and "Alpha" in csv
    overall = main.attorney_cohort(name="Counsel", cohort="all")
    assert overall["size"] == 2 and overall["attorney"]["match_rate"] == 100 and overall["cohort"]["match_rate"] == 50
    assert main.attorney_cohort(name="Counsel", cohort="case_type")["size"] == 1
    assert main.attorney_cohort(name="Counsel", cohort="period")["size"] == 1


def test_compare_cases_parses_topics_and_handles_missing_lists(monkeypatch):
    data = {
        'a': {'opinion': {'case_number':'a', 'topics':"['evidence', 'contracts']", 'rsa_citations':None, 'outcome':'affirmed', 'author':'A', 'lower_court_type':'superior'}, 'text':'First opinion'},
        'b': {'opinion': {'case_number':'b', 'topics':"['evidence']", 'rsa_citations':'[]', 'outcome':'reversed', 'author':'B', 'lower_court_type':'district'}, 'text':'Second opinion'},
    }
    monkeypatch.setattr(main, 'get_opinion', lambda number: data[number])
    result = main.compare_cases('a', 'b')
    assert result['first']['text'] == 'First opinion'
    assert result['reasons'] == ['Both involve: evidence']
    assert main.compare_cases('a', 'a')['reasons'] == []


def test_firm_review_aggregates_source_aliases(monkeypatch, tmp_path):
    pd.DataFrame([
        {'full_name':'Firm LLP','short_name':'F LLP','review_status':'verified'},
        {'full_name':'Firm LLP','short_name':'Firm','review_status':'verified'},
        {'full_name':'Firm LLP','short_name':'Ignored','review_status':'skipped — duplicate'},
    ]).to_csv(tmp_path / 'nh_supreme_court_firms_enriched_v7.csv',index=False)
    monkeypatch.setattr(main,'data_root',lambda:tmp_path)
    monkeypatch.setattr(main,'oral_argument_people',lambda:{'firms':[{'firm_name':'Firm LLP','total_arguments':3,'unique_attorneys':2}]})
    row=main.firm_review()['items'][0]
    assert row['Known abbreviation(s)'] == 'F LLP, Firm'
    assert row['Source review status'] == 'verified'
    assert row['Feedback action'] == 'Keep' and row['Arguments'] == 3


def test_attorney_profile_combines_lower_court_judges(monkeypatch):
    from utils import data_loader
    monkeypatch.setattr(main, 'oral_argument_people', lambda: {'attorneys':[{'attorney_name':'Counsel','cases':[]}], 'firms':[], 'firm_metadata':{}})
    monkeypatch.setattr(main, 'argument_records', lambda: [])
    monkeypatch.setattr(data_loader, 'load_argument_dispositions', lambda: pd.DataFrame([
        {'argument_id':'a','term_year':2024,'resolution_type':'opinion','days_to_disposition':30,'case_type':'civil','lower_court':'Superior Court (Smith, J.)','outcome':'affirmed'},
        {'argument_id':'b','term_year':2024,'resolution_type':'opinion','days_to_disposition':40,'case_type':'civil','lower_court':'Superior Court (Jones, J.)','outcome':'affirmed'},
    ]))
    monkeypatch.setattr(data_loader, 'load_argument_participants', lambda: pd.DataFrame([{'argument_id':i,'attorney_name':'Counsel','firm':'Firm'} for i in ('a','b')]))
    monkeypatch.setattr(data_loader, 'load_argument_topics', lambda: pd.DataFrame())
    assert main.oral_argument_profile(kind='attorney',name='Counsel')['dispositions']['lower_courts'] == [{'name':'Superior Court','count':2}]


def test_statute_search_filters_year_and_matches_literal_text(monkeypatch):
    monkeypatch.setattr(main, 'opinions', lambda: pd.DataFrame([
        {'case_number':'a','case_name':'Alpha','term_year':2023,'rsa_citations':'RSA 135:1','citation':'A','outcome':'affirmed'},
        {'case_number':'b','case_name':'Beta','term_year':2024,'rsa_citations':'RSA 135:2','citation':'B','outcome':'reversed'},
        {'case_number':'c','case_name':'Gamma','term_year':2024,'rsa_citations':'RSA 13X','citation':'C','outcome':'affirmed'},
    ]))
    result=main.analysis_statute_search(year_min=2024,year_max=2024,rsa='rsa 135')
    assert [row['case_number'] for row in result['items']] == ['b']
    assert main.analysis_statute_search(year_min=2023,year_max=2024,rsa='13.')['items'] == []
    assert main.analysis_statute_search(year_min=2023,year_max=2024,rsa='  ')['items'] == []


def test_trial_court_breakdown_sorts_by_court_type_and_total():
    frame = pd.DataFrame([
        {'court_type':'Superior Court','court_base':'Beta','outcome_label':'Affirmed'},
        {'court_type':'Circuit Court','court_base':'Alpha','outcome_label':'Affirmed'},
        {'court_type':'Circuit Court','court_base':'Zeta','outcome_label':'Reversed'},
        {'court_type':'Circuit Court','court_base':'Zeta','outcome_label':'Affirmed & Remanded'},
    ])
    rows = main._trial_breakdown(frame, ['court_type', 'court_base'])
    assert [r['court_base'] for r in rows] == ['Zeta', 'Alpha', 'Beta']
    assert rows[0]['Total'] == 2 and rows[0]['Affirmed & Remanded'] == 1


def test_transcript_reader_returns_only_case_attorney_statistics(monkeypatch, tmp_path):
    monkeypatch.setattr(main, 'data_root', lambda: tmp_path)
    monkeypatch.setattr(main, 'argument_records', lambda: [{'case_number':'2024-0001','case_name':'Example'}])
    roster = {'case_attorneys': {'2024-0001':[{'name':'Counsel'}]}, 'attorney_stats':[{'attorney_name':'Counsel','total_arguments':3},{'attorney_name':'Other','total_arguments':10}]}
    monkeypatch.setattr(main, '_optional_json', lambda name, default: roster if name == 'oral_arguments_attorney_stats.json' else default)
    result = main.argument_detail('2024-0001')
    assert result['attorneys'] == [{'name':'Counsel'}]
    assert result['attorney_stats'] == [{'attorney_name':'Counsel','total_arguments':3}]


def test_order_sort_applies_before_pagination(monkeypatch):
    rows = pd.DataFrame([
        {'case_number':'1','case_name':'Zulu','term_year':2024,'date_issued':'2024-03-01','case_type':'civil','order_source':'case_order'},
        {'case_number':'2','case_name':'Alpha','term_year':2024,'date_issued':'2024-01-01','case_type':'civil','order_source':'case_order'},
        {'case_number':'3','case_name':'Beta','term_year':2024,'date_issued':'2024-02-01','case_type':'civil','order_source':'case_order'},
    ])
    monkeypatch.setattr(main, 'orders', lambda: rows)
    result = main.list_orders(year=[],case_type=[],source=[],q='',offset=1,limit=1,sort='case_name',direction='asc')
    assert result['count'] == 3 and result['items'][0]['case_name'] == 'Beta'
    result = main.list_orders(year=[],case_type=[],source=[],q='',offset=0,limit=1,sort='date_issued',direction='desc')
    assert result['items'][0]['case_name'] == 'Zulu'


def test_order_loader_normalizes_mixed_date_formats(tmp_path):
    processed = tmp_path / 'processed'
    processed.mkdir()
    pd.DataFrame([{'case_number':'a','case_name':'Alpha','date_issued':'2024-01-02','term_year':2024}]).to_csv(processed / 'case_orders.csv',index=False)
    pd.DataFrame([{'case_number':'b','case_name':'Beta','date_issued':'12/13/2017','term_year':2017}]).to_csv(processed / '3jx_orders.csv',index=False)
    result = main._read_orders(str(tmp_path), 1, 1)
    assert result.loc[result['case_number']=='b','date_issued'].iloc[0] == pd.Timestamp('2017-12-13')


def test_topics_rsa_tracker_matches_years_and_literal_query(monkeypatch):
    monkeypatch.setattr(main, 'opinions', lambda: pd.DataFrame([
        {'case_number':'a','case_name':'Alpha','term_year':2023,'rsa_citations':'RSA 135:1','citation':'A','outcome':'affirmed'},
        {'case_number':'b','case_name':'Beta','term_year':2024,'rsa_citations':'RSA 135:2','citation':'B','outcome':'reversed_and_remanded'},
        {'case_number':'c','case_name':'Gamma','term_year':2024,'rsa_citations':'RSA 13X','citation':'C','outcome':'affirmed'},
    ]))
    result = main.topics_rsa(year_min=2024,year_max=2024,q='135')
    assert result['count'] == 1 and result['items'][0]['case_number'] == 'b'
    assert result['outcomes'] == [{'key':'reversed_and_remanded','count':1}]
    assert result['chart']['data'][0]['type'] == 'bar'
    assert main.topics_rsa(year_min=2023,year_max=2024,q='13.')['count'] == 0


def test_compare_options_preserve_source_order_and_undated_cases(monkeypatch):
    monkeypatch.setattr(main,'opinions',lambda:pd.DataFrame([
        {'case_number':'b','case_name':'Beta','term_year':None},
        {'case_number':'a','case_name':'Alpha','term_year':2024},
        {'case_number':None,'case_name':'Missing','term_year':2024},
    ]))
    assert main.compare_case_options()['items'] == [{'case_number':'b','case_name':'Beta'}, {'case_number':'a','case_name':'Alpha'}]


def test_legal_case_options_preserve_source_order_and_include_undated_cases(monkeypatch):
    monkeypatch.setattr(main,'opinions',lambda:pd.DataFrame([
        {'case_number':'b','case_name':'Beta','term_year':None},
        {'case_number':'a','case_name':'Alpha','term_year':2024},
        {'case_number':None,'case_name':'Missing','term_year':2024},
    ]))
    assert main.legal_case_options()['items'] == [
        {'case_number':'b','case_name':'Beta'},
        {'case_number':'a','case_name':'Alpha'},
    ]


def test_compare_does_not_report_missing_metadata_as_common(monkeypatch):
    cases = {'a': {'opinion': {'topics':None,'rsa_citations':None,'outcome':None,'author':None,'lower_court_type':None}},
             'b': {'opinion': {'topics':None,'rsa_citations':None,'outcome':None,'author':None,'lower_court_type':None}}}
    monkeypatch.setattr(main,'get_opinion',lambda key:cases[key])
    assert main.compare_cases('a','b')['reasons'] == ['Similar legal issues']
