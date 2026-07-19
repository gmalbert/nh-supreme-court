from urllib.parse import parse_qs, urlparse

from utils.chat_formatter import ResponseFormatter, normalize_case_links
from utils.chat_retriever import CaseRetriever


def test_chat_case_url_uses_streamlit_slug(monkeypatch):
    monkeypatch.setattr("utils.chat_retriever.supreme_available", lambda: True)
    monkeypatch.setattr(
        "utils.chat_retriever.supreme_search",
        lambda query, top_k: [{"name": "Furman v. Georgia", "term": "1971", "href": "example"}],
    )
    monkeypatch.setattr(CaseRetriever, "_get_supreme_court_snippet", lambda self, href: "summary")

    result = CaseRetriever().retrieve_cases("death penalty", top_k=1)[0]
    parsed = urlparse(result["url"])
    assert parsed.path == "/Cases"
    assert parse_qs(parsed.query) == {
        "q": ["Furman v. Georgia"],
        "case": ["Furman v. Georgia"],
    }


def test_empty_provider_response_gets_linked_narrative():
    case = {"name": "Furman v. Georgia", "term": "1971", "url": "/1_Cases?q=Furman"}
    rendered = ResponseFormatter().ensure_narrative("", [case])
    assert "Furman v. Georgia" in rendered
    assert "source summaries" in rendered


def test_legacy_narrative_links_are_upgraded():
    old_links = (
        "[*Davis v. United States*](1_Cases.py?q=Davis+v.+United+States&case=Davis+v.+United+States)\n"
        "[*Furman v. Georgia*](/?q=Furman+v.+Georgia&case=Furman+v.+Georgia)"
    )
    repaired = normalize_case_links(old_links)
    assert "1_Cases.py" not in repaired
    assert "](/?q=" not in repaired
    assert repaired.count("](/Cases?q=") == 2
