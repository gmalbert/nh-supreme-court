from utils.chat_retriever import (
    CaseRetriever,
    build_retrieval_query,
    merge_retrieved_cases,
)


CASES = [
    {"name": "Mapp v. Ohio", "href": "mapp", "source": "supreme-court"},
    {"name": "Weeks v. United States", "href": "weeks", "source": "supreme-court"},
]


def test_standalone_question_is_not_rewritten():
    question = "What cases established the exclusionary rule?"
    assert build_retrieval_query(question, "old topic", CASES) == question


def test_referential_followup_includes_previous_topic_and_cases():
    query = build_retrieval_query("What did the dissent say?", "Explain the exclusionary rule.", CASES)
    assert "Explain the exclusionary rule" in query
    assert "Mapp v. Ohio" in query
    assert "Weeks v. United States" in query


def test_prior_and_new_cases_are_deduplicated_by_href():
    fresh = [CASES[0].copy(), {"name": "United States v. Leon", "href": "leon"}]
    merged = merge_retrieved_cases(fresh, CASES, include_previous=True)
    assert [case["href"] for case in merged] == ["mapp", "weeks", "leon"]


def test_context_labels_holding_and_handles_missing_value():
    retriever = CaseRetriever()
    context = retriever.format_context_for_llm([
        {**CASES[0], "facts": "Police searched a home.", "question": "Was the evidence admissible?", "holding": "The exclusionary rule applies to the states."},
        {**CASES[1], "holding": ""},
    ])
    assert "Holding: The exclusionary rule applies to the states." in context
    assert "Holding: Not available in the supplied case record." in context
    assert "nan" not in context
    assert "None" not in context


def test_decision_summary_includes_split_and_justice_names():
    decisions = '[{"votes": [' \
        '{"member": {"name": "Justice One"}, "vote": "majority"},' \
        '{"member": {"name": "Justice Two"}, "vote": "dissent"}' \
        ']}]'
    summary = CaseRetriever._summarize_decisions(decisions)
    assert summary == {
        "vote_split": "1-1",
        "majority_justices": "Justice One",
        "minority_justices": "Justice Two",
    }


def test_decision_summary_includes_opinion_authors():
    decisions = '[{"votes": [' \
        '{"member": {"name": "Justice Stewart"}, "vote": "majority", "opinion_type": "majority"},' \
        '{"member": {"name": "Justice White"}, "vote": "minority", "opinion_type": "dissent"}' \
        ']}]'
    summary = CaseRetriever._summarize_decisions(decisions)
    assert summary["opinion_authors"] == "majority: Justice Stewart; dissent: Justice White"
    assert summary["majority_opinion_authors"] == "Justice Stewart"
    assert summary["dissent_authors"] == "Justice White"
