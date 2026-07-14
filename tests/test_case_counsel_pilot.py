"""Regression tests for the evidence-backed case-counsel pilot."""

from pathlib import Path

from scripts.build_pdf_attorney_roster_overrides import add_consolidated_roster_aliases, build_facts, candidate_names, infer_firm, infer_side, parse_official_counsel, transcript_confirms_oral_advocate


def test_candidate_names_keeps_suffixes_and_multiple_counsel():
    assert candidate_names("John L. Riff, IV and Jane A. Doe") == ["John L. Riff, IV", "Jane A. Doe"]


def test_build_facts_preserves_provenance_and_queues_uncertain_side():
    candidates = {
        "2014-0001": [
            {
                "attorney_raw": "Jane A. Doe",
                "firm": "",
                "side": "unknown",
                "confidence": "low",
                "source_file": "2015.pdf",
                "source_page": "3",
                "source_sha256": "abc",
                "source_locator": "docket row 2014-0001",
                "evidence_text": "(Jane A. Doe)",
            }
        ]
    }
    facts, selected = build_facts(candidates, {"2014-0001"}, 100)

    assert selected == ["2014-0001"]
    assert facts[0]["role"] == "scheduled_oral_candidate"
    assert facts[0]["review_status"] == "needs_review"
    assert facts[0]["source_page"] == 3
    assert facts[0]["source_sha256"] == "abc"


def test_side_inference_never_uses_opposing_party_context():
    segment = "State of New Hampshire Attorney General (Jane A. Doe) v. Appellate Defender (John B. Roe)"
    assert infer_side(segment, segment.index("Jane")) == ("state", "high")
    assert infer_side(segment, segment.index("John")) == ("defendant", "high")


def test_firm_inference_reads_the_pdf_line_immediately_before_counsel():
    segment = "In the Matter of A and B\nPPE&C\n(Doreen F. Connor) (15 min.)"
    assert infer_firm(segment, segment.index("(")) == "PPE&C"


def _roles(docket: str) -> set[tuple[str, str]]:
    text = Path(f"data/processed/text/{docket}.txt").read_text(encoding="utf-8")
    return {(fact["name"], fact["role"]) for fact in parse_official_counsel(docket, text, "https://example.test/decision.pdf")}


def test_published_appearance_regressions():
    sanborn = _roles("2013-0882")
    assert ("Mark L. Sisti", "oral_advocate") in sanborn
    assert ("Jared Bedrick", "brief_counsel") in sanborn
    assert ("Jared Bedrick", "oral_advocate") not in sanborn

    rokowski = _roles("2014-0617")
    assert ("Danielle Richey Santuccio", "oral_advocate") in rokowski
    assert ("Donald M. Ekberg", "oral_advocate") in rokowski

    broderick = _roles("2014-0224")
    assert ("Thomas Morgan", "oral_advocate") in broderick
    assert ("Lawrence M. Edelman", "oral_advocate") in broderick

    mutrie = _roles("2014-0402")
    assert ("Donald L. Smith", "oral_advocate") in mutrie
    assert all(name != "Bradley M. Lown" for name, _ in mutrie)

    scott = _roles("2014-0407")
    assert ("Dana Alan Curhan", "oral_advocate") in scott
    assert all(name != "Bradford R. Stanton" for name, _ in scott)

    eschenbrenner = _roles("2014-0116")
    assert ("Stephen D. Fuller", "oral_advocate") in eschenbrenner
    assert ("Christopher M. Johnson", "oral_advocate") in eschenbrenner


def test_order_transcript_can_confirm_scheduled_counsel():
    text = Path("data/processed/oral_arguments/text/2014-0081.txt").read_text(encoding="utf-8")
    assert transcript_confirms_oral_advocate(text, "Christopher J. Poulin")


def test_consolidated_repository_key_inherits_component_pdf_roster():
    candidates = {"2022-0353": [{"attorney_raw": "Jane A. Doe", "source_locator": "docket row 2022-0353"}]}
    add_consolidated_roster_aliases(candidates, {"2022-0353-2022-0415"})
    assert candidates["2022-0353-2022-0415"][0]["attorney_raw"] == "Jane A. Doe"
