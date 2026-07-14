from scripts import build_dataset


def test_normalize_case_name_strips_single_and_combined_docket_prefixes():
    assert build_dataset.normalize_case_name(
        "2013-0392. State of New Hampshire v. Kevin Balch"
    ) == "State of New Hampshire v. Kevin Balch"
    assert build_dataset.normalize_case_name(
        "2013-0411 and 2014-0503, In the Matter of Diana Wolters and John Wolters"
    ) == "In the Matter of Diana Wolters and John Wolters"


def test_normalize_record_recovers_caption_from_modification_order(monkeypatch):
    monkeypatch.setattr(
        build_dataset,
        "caption_from_modification_order",
        lambda _case_number: "State of New Hampshire v. Samuel Pennock",
    )

    record = build_dataset.normalize_record(
        {
            "case_number": "2014-0112",
            "case_name": "(Modified December 3, 2015: see court order)",
        }
    )

    assert record["case_name"] == "State of New Hampshire v. Samuel Pennock"
    assert "_exclude_from_case_explorer" not in record


def test_normalize_record_excludes_unrecoverable_modification_notice(monkeypatch):
    monkeypatch.setattr(build_dataset, "caption_from_modification_order", lambda _: None)

    record = build_dataset.normalize_record(
        {"case_number": "unknown", "case_name": "Modified October 3, 2022 - see court order"}
    )

    assert record["_exclude_from_case_explorer"] is True
