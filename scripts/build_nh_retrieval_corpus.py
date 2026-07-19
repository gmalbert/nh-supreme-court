"""Build the normalized case corpus for NH Supreme Court retrieval.

Output: data/retrieval/case_documents.parquet

Each row is one case with fields expected by the retrieval system:
    case_id            — stable hash of case_number
    name, normalized_name
    href, term, docket_number, citation
    facts, question, holding, description
    retrieval_text     — combined label:text for retrieval
    decisions_json     — JSON-encoded vote/author data
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "processed" / "opinions.csv"
OUT_DIR = ROOT / "data" / "retrieval"
OUT = OUT_DIR / "case_documents.parquet"


def clean(value: object) -> str:
    """Clean HTML and normalize whitespace."""
    if value is None:
        return ""
    if not isinstance(value, (list, dict)) and isinstance(value, float) and pd.isna(value):
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value)))
    return re.sub(r"\s+", " ", text).strip()


def normalize_case_name(value: str) -> str:
    """Normalize case name for matching (lowercase, v standardization)."""
    if not value:
        return ""
    v = value.casefold().replace("versus", " v ")
    v = re.sub(r"\bvs?\.?\b", " v ", v)
    v = re.sub(r"[^a-z0-9]+", " ", v)
    return re.sub(r"\s+", " ", v).strip()


def stable_case_id(case_number: str, name: str, term: str) -> str:
    """Generate stable case ID from case_number or fallback to term:name."""
    key = (case_number or f"{term}:{name}").strip()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def build_decisions_json(row: dict) -> str:
    """Build Oyez-style decisions JSON from NH vote fields."""
    decisions = []

    # Extract vote information
    vote_data = {
        "majority": clean(row.get("majority")),
        "dissent": clean(row.get("dissent")),
        "concur_separate": clean(row.get("concur_separate")),
        "not_participating": clean(row.get("not_participating")),
        "vote_string": clean(row.get("vote_string")),
        "is_unanimous": row.get("is_unanimous"),
        "has_dissent": row.get("has_dissent"),
    }

    # Build decision object
    decision = {
        "description": clean(row.get("outcome")),
        "votes": vote_data,
        "majority_vote": vote_data.get("majority", ""),
        "minority_vote": vote_data.get("dissent", ""),
    }

    decisions.append(decision)
    return json.dumps(decisions)


def main() -> None:
    """Build the retrieval corpus from NH opinions CSV."""
    print(f"Loading opinions from {SOURCE}...")

    if not SOURCE.exists():
        print(f"Error: {SOURCE} does not exist!")
        print("Run the data pipeline first to generate opinions.csv")
        return

    df = pd.read_csv(SOURCE, dtype=str)
    print(f"Loaded {len(df):,} opinions")

    # Create output directory
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for idx, record in enumerate(df.to_dict("records"), 1):
        if idx % 100 == 0:
            print(f"Processing {idx:,}/{len(df):,}...", end="\r")

        case_number = clean(record.get("case_number"))
        name = clean(record.get("case_name"))
        term = clean(record.get("term_year"))
        citation = clean(record.get("citation"))
        docket = clean(record.get("docket_numbers"))

        # Map NH fields to retrieval fields
        summary = clean(record.get("summary_paragraph"))
        outcome = clean(record.get("outcome"))
        author = clean(record.get("author_display") or record.get("author"))

        # Build retrieval text from available fields
        fields = {
            "name": name,
            "summary": summary,
            "outcome": outcome,
            "author": author,
            "citation": citation,
            "topics": clean(record.get("topics")),
            "court": clean(record.get("lower_court")),
        }

        # facts, question, holding for compatibility with retrieval system
        # NH doesn't have explicit fact/question sections, use summary for all
        facts = summary
        question = f"Appeal from {clean(record.get('lower_court'))}" if record.get("lower_court") else ""
        holding = outcome
        description = summary

        retrieval_text = "\n".join(
            f"{label}: {value}" for label, value in fields.items() if value
        )

        rows.append({
            "case_id": stable_case_id(case_number, name, term),
            "name": name,
            "normalized_name": normalize_case_name(name),
            "href": case_number,  # Use case_number as unique identifier
            "term": term,
            "docket_number": docket,
            "citation": citation,
            "facts": facts,
            "question": question,
            "holding": holding,
            "description": description,
            "retrieval_text": retrieval_text,
            "decisions_json": build_decisions_json(record),
            "oral_argument_audio": json.dumps([]),  # NH doesn't have this yet
            "raw_metadata_json": json.dumps({
                "lower_court": clean(record.get("lower_court")),
                "lower_court_type": clean(record.get("lower_court_type")),
                "lower_court_judge": clean(record.get("lower_court_judge")),
                "case_type": clean(record.get("case_type")),
                "appeal_type": clean(record.get("appeal_type")),
                "topics": clean(record.get("topics")),
                "rsa_citations": clean(record.get("rsa_citations")),
                "standard_of_review": clean(record.get("standard_of_review")),
                "word_count": clean(record.get("word_count")),
            }),
        })

    print(f"\nBuilding corpus with {len(rows):,} cases...")
    corpus = pd.DataFrame(rows)

    # Write to parquet
    corpus.to_parquet(OUT, index=False, engine="pyarrow")
    print(f"✓ Wrote {OUT}")
    print(f"  {len(corpus):,} cases")
    print(f"  {len(corpus.columns)} columns")
    print(f"  {OUT.stat().st_size / 1024 / 1024:.1f} MB")

    # Show sample
    print("\nSample case:")
    sample = corpus.iloc[0]
    print(f"  Name: {sample['name']}")
    print(f"  Term: {sample['term']}")
    print(f"  Citation: {sample['citation']}")
    print(f"  Retrieval text: {sample['retrieval_text'][:200]}...")


if __name__ == "__main__":
    main()
