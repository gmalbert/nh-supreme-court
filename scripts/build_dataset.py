"""
scripts/build_dataset.py
-------------------------
Merge per-year JSON files into master all_opinions.json and opinions.csv.
Also builds case_orders.csv.

Usage:
    python scripts/build_dataset.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROCESSED_DIR = ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
CASE_TYPE_OVERRIDES_PATH = ROOT / "data" / "case_type_manual_overrides.csv"

# Columns to flatten from nested dicts for the CSV export
FLAT_COLUMNS = [
    "case_number", "citation", "citation_year", "citation_seq",
    "case_name", "pdf_url", "date_argued", "date_issued",
    "days_to_decision", "term_year", "lower_court", "lower_court_type", "lower_court_judge",
    "case_type", "appeal_type", "outcome", "author", "author_display",
    "majority", "dissent", "concur_separate", "not_participating",
    "vote_string", "is_unanimous", "has_dissent", "has_separate_concurrence",
    "topics", "rsa_citations", "rsa_primary", "involves_statutory_interpretation",
    "standard_of_review", "summary_paragraph", "word_count",
    "opinion_type", "parse_version", "parse_timestamp", "parse_confidence",
]

OUTCOME_NORMALIZATION = {
    "remaned": "remanded",
}

SUMMARY_LEADING_JUNK_RE = re.compile(r"^\s*[][(){}\"'“”‘’`]+\s*")
SUMMARY_TRAILING_JUNK_RE = re.compile(r"\s*[][(){}\"'“”‘’`]+\s*$")
RSA_CHAPTER_RE = re.compile(
    r"^RSA\s+chapter\s+(.+)$",
    re.IGNORECASE,
)

STATE_V_CASE_RE = re.compile(
    r"^state(?:\s+of\s+new\s+hampshire)?\s+v\.\s+",
    re.IGNORECASE,
)

FAMILY_NAME_KEYWORDS = {
    "domestic violence",
    "divorce",
    "custody",
    "parenting",
    "parental rights",
    "child support",
    "visitation",
    "marital",
    "adoption",
}

FAMILY_RSA_MARKERS = {
    "458",
    "461-a",
    "461a",
    "170-c",
    "170c",
    "169-c",
    "169c",
    "173-b",
    "173b",
}

CRIMINAL_RSA_MARKERS = {
    "318-b",
    "318b",
    "625",
    "626",
    "627",
    "628",
    "629",
    "630",
    "631",
    "632",
    "633",
    "634",
    "635",
    "636",
    "637",
    "638",
    "639",
    "640",
    "641",
    "642",
    "643",
    "644",
    "645",
    "646",
    "647",
    "648",
    "649",
    "650",
    "651",
}


def normalize_outcome(value):
    if value is None:
        return value
    key = str(value).strip().lower()
    return OUTCOME_NORMALIZATION.get(key, key)


def normalize_summary(value):
    if value is None:
        return value
    text = str(value).replace("\ufffd", "").strip()
    text = SUMMARY_LEADING_JUNK_RE.sub("", text)
    text = SUMMARY_TRAILING_JUNK_RE.sub("", text)
    return text.strip()


def normalize_rsa_citations(values):
    if not isinstance(values, list):
        return values

    cleaned = []
    for item in values:
        raw = re.sub(r"\s+", " ", str(item).strip())
        if re.fullmatch(r"RSA\s+chapters?", raw, flags=re.IGNORECASE):
            continue
        m = RSA_CHAPTER_RE.match(raw)
        if m:
            raw = f"RSA {m.group(1).strip()}"
        cleaned.append(raw)

    # Deduplicate while preserving order.
    return list(dict.fromkeys(cleaned))


def parse_listlike(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            import ast
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def derive_case_type(topics: list[str], fallback=None) -> str | None:
    if not topics:
        return fallback
    topic_set = set(str(t) for t in topics)
    if "family_law" in topic_set or "domestic_violence" in topic_set:
        return "family/domestic"
    if "criminal" in topic_set:
        return "criminal"
    return "civil"


def is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip() == ""


def parse_rsa_markers(value) -> set[str]:
    citations = parse_listlike(value)
    markers: set[str] = set()
    for citation in citations:
        text = str(citation).lower()
        for match in re.finditer(r"rsa\s+([0-9]+(?:-[a-z])?)", text):
            markers.add(match.group(1).replace(" ", ""))
    return markers


def infer_case_type_from_fallback(case_name, rsa_citations) -> tuple[str | None, str, str]:
    name = str(case_name or "").strip()
    name_l = name.lower()

    if STATE_V_CASE_RE.match(name_l):
        return "criminal", "high", "state_v_case_name"

    if any(k in name_l for k in FAMILY_NAME_KEYWORDS):
        return "family/domestic", "high", "family_keyword_case_name"

    markers = parse_rsa_markers(rsa_citations)
    has_family_marker = any(m in FAMILY_RSA_MARKERS for m in markers)
    has_criminal_marker = any(m in CRIMINAL_RSA_MARKERS for m in markers)

    if has_family_marker and not has_criminal_marker:
        return "family/domestic", "medium", "family_rsa_marker"

    if has_criminal_marker and not has_family_marker:
        return "criminal", "medium", "criminal_rsa_marker"

    if re.match(r"^[A-Z]\.[A-Z]\.\s+v\.\s+[A-Z]\.[A-Z]\.", name):
        return "family/domestic", "low", "initials_case_name_pattern"

    return None, "none", "insufficient_signals"


def default_override_case_type(case_name) -> tuple[str, str]:
    name = str(case_name or "").strip()
    name_l = name.lower()

    # If the State is the leading party, default criminal.
    if STATE_V_CASE_RE.match(name_l):
        return "criminal", "default_state_v_caption"

    # Family framing by caption style.
    if name_l.startswith("in the matter of "):
        return "family/domestic", "default_in_the_matter_of"

    # Common anonymized family-style caption.
    if re.match(r"^[A-Z]\.[A-Z]\.\s+v\.\s+[A-Z]\.[A-Z]\.", name):
        return "family/domestic", "default_initials_pattern"

    # Criminal appellate caption pattern.
    if re.search(r"\bv\.\s+state\s+of\s+new\s+hampshire\b", name_l):
        return "criminal", "default_v_state_caption"

    # Conservative explicit default for unresolved records.
    return "civil", "default_fallback_civil"


def sync_case_type_overrides(orders: list[dict]) -> dict[str, str]:
    missing_rows = [
        o for o in orders
        if str(o.get("opinion_type", "")).strip().lower() == "case_order"
        and is_missing(o.get("case_type"))
    ]

    generated = []
    for o in missing_rows:
        default_case_type, reason = default_override_case_type(o.get("case_name"))
        generated.append(
            {
                "case_number": str(o.get("case_number", "")).strip(),
                "case_name": o.get("case_name"),
                "override_case_type": default_case_type,
                "override_reason": reason,
            }
        )

    gen_df = pd.DataFrame(generated)

    if CASE_TYPE_OVERRIDES_PATH.exists():
        existing = pd.read_csv(CASE_TYPE_OVERRIDES_PATH, dtype=str).fillna("")
    else:
        existing = pd.DataFrame(columns=["case_number", "case_name", "override_case_type", "override_reason"])

    required_cols = ["case_number", "case_name", "override_case_type", "override_reason"]
    for col in required_cols:
        if col not in existing.columns:
            existing[col] = ""

    existing = existing[required_cols]

    if not gen_df.empty:
        if existing.empty:
            merged = gen_df
        else:
            merged = existing.merge(
                gen_df,
                on="case_number",
                how="outer",
                suffixes=("", "_generated"),
            )
            merged["case_name"] = merged["case_name"].where(
                merged["case_name"].astype(str).str.strip().ne(""),
                merged["case_name_generated"],
            )
            merged["override_case_type"] = merged["override_case_type"].where(
                merged["override_case_type"].astype(str).str.strip().ne(""),
                merged["override_case_type_generated"],
            )
            merged["override_reason"] = merged["override_reason"].where(
                merged["override_reason"].astype(str).str.strip().ne(""),
                merged["override_reason_generated"],
            )
            merged = merged[required_cols]
    else:
        merged = existing

    CASE_TYPE_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = merged.sort_values("case_number").drop_duplicates(subset=["case_number"], keep="first")
    merged.to_csv(CASE_TYPE_OVERRIDES_PATH, index=False, encoding="utf-8-sig")

    override_map = {}
    for _, row in merged.iterrows():
        case_number = str(row.get("case_number", "")).strip()
        override = str(row.get("override_case_type", "")).strip().lower()
        if case_number and override in {"civil", "criminal", "family/domestic"}:
            override_map[case_number] = override

    return override_map


# Patterns that signal the end of a lower court name
_LC_STOP_RE = re.compile(
    r"Case\s*No\.?|Citation\s*:|Order\s*No\.?|\bNo\.\s*\d{4}|\d{4}-\d{4}",
    re.IGNORECASE,
)
# Matches a judge-name parenthetical like "(Smith, J.)", "(St. Hilaire, J.)", or "(Jones, C.J.)"
_LC_JUDGE_PAREN_RE = re.compile(r"\([A-Za-z\s.'\u2018\u2019-]+,\s*(?:C\.J\.|JJ\.|J\.)\)")

def normalize_case_name(name) -> str:
    """Replace U+FFFD replacement chars (bad PDF decode) with apostrophes."""
    if not name or not isinstance(name, str):
        return name
    import re as _re
    return _re.sub(r"(?<=\w)\ufffd(?=\w)", "'", name)


def normalize_lower_court(value) -> str | None:
    """Trim lower court strings that include trailing case-number / sentence noise."""
    if not value or not isinstance(value, str):
        return value
    # Stop at first newline
    snippet = value.split("\n")[0]
    # Stop at case-number / citation markers
    m = _LC_STOP_RE.search(snippet)
    if m:
        snippet = snippet[: m.start()]
    # If there's a judge parenthetical "(Smith, J.)", end the string there
    m_judge = _LC_JUDGE_PAREN_RE.search(snippet)
    if m_judge:
        snippet = snippet[: m_judge.end()]
    # Strip unclosed parentheticals like "(Quigley" or "(Abramson"
    paren_pos = snippet.rfind("(")
    close_pos = snippet.rfind(")")
    if paren_pos > close_pos:
        snippet = snippet[:paren_pos]
    snippet = re.sub(r"\s+", " ", snippet).strip().rstrip(" ,;-")
    # Drop sentence-fragment leads ("the ", "l in ", "in ")
    snippet = re.sub(r"^(?:the\s+|l\s+in\s+|in\s+)", "", snippet, flags=re.IGNORECASE)
    # Discard if no "court" reference (captured garbage mid-text)
    if snippet and "court" not in snippet.lower():
        return None
    # Canonicalize Superior Court — strip trailing noise or recover from fragment
    if re.search(r"superior\s+court", snippet, re.IGNORECASE):
        m_sc = re.match(
            r"^(?:[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*\s+)?Superior\s+Court"
            r"(?:\s+\([A-Za-z\s.'\u2018\u2019-]+,\s*(?:C\.J\.|JJ\.|J\.)\))?",
            snippet,
        )
        snippet = m_sc.group(0).strip().rstrip(" ,;-") if m_sc else "Superior Court"
    # Normalize U.S. District Court variants to a single canonical form
    if re.search(r"u\.?s\.?\s+district\s+court", snippet, re.IGNORECASE):
        snippet = "U.S. District Court"
    return snippet or None


def normalize_record(rec: dict) -> dict:
    out = dict(rec)
    out["case_name"] = normalize_case_name(out.get("case_name"))
    out["lower_court"] = normalize_lower_court(out.get("lower_court"))
    out["outcome"] = normalize_outcome(out.get("outcome"))
    out["summary_paragraph"] = normalize_summary(out.get("summary_paragraph"))
    out["rsa_citations"] = normalize_rsa_citations(out.get("rsa_citations"))

    rsa_citations = out.get("rsa_citations")
    if isinstance(rsa_citations, list) and rsa_citations:
        out["rsa_primary"] = rsa_citations[0]

    topics = parse_listlike(out.get("topics"))
    if topics:
        out["case_type"] = derive_case_type(topics, fallback=out.get("case_type"))

    if str(out.get("opinion_type", "")).strip().lower() == "case_order":
        case_type_was_null = is_missing(out.get("case_type"))
        out["_case_type_was_null"] = case_type_was_null
        topic_case_type = derive_case_type(topics)
        if topic_case_type:
            out["case_type"] = topic_case_type
            out["_case_type_inference_confidence"] = "high"
            out["_case_type_inference_reason"] = "topic_based"
        elif case_type_was_null:
            inferred, confidence, reason = infer_case_type_from_fallback(
                out.get("case_name"),
                out.get("rsa_citations"),
            )
            out["case_type"] = inferred
            out["_case_type_inference_confidence"] = confidence
            out["_case_type_inference_reason"] = reason
        else:
            out["_case_type_inference_confidence"] = "high"
            out["_case_type_inference_reason"] = "existing_case_type"

    return out


def load_year_jsons(pattern: str) -> list[dict]:
    records = []
    for path in sorted(PROCESSED_DIR.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            year_records = [normalize_record(r) for r in json.load(fh)]
        print(f"  Loaded {len(year_records)} records from {path.name}")
        records.extend(year_records)
    return records


def to_flat_csv(records: list[dict], out_path: Path):
    rows = []
    for rec in records:
        row = {}
        for col in FLAT_COLUMNS:
            val = rec.get(col)
            # Serialize list/dict fields as strings for CSV
            if isinstance(val, (list, dict)):
                row[col] = str(val)
            else:
                row[col] = val
        rows.append(row)
    df = pd.DataFrame(rows, columns=FLAT_COLUMNS)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"  Saved CSV → {out_path} ({len(df)} rows)")
    return df


def main():
    print("\n=== Building master dataset ===")

    # ── Opinions ──────────────────────────────────────────────────────────────
    opinions = load_year_jsons("opinions_*.json")
    if opinions:
        master_path = PROCESSED_DIR / "all_opinions.json"
        with open(master_path, "w", encoding="utf-8") as fh:
            json.dump(opinions, fh, indent=2, ensure_ascii=False)
        print(f"  Saved all_opinions.json ({len(opinions)} total)")

        to_flat_csv(opinions, PROCESSED_DIR / "opinions.csv")
    else:
        print("  No opinion records found — run parse_opinions.py first")

    # ── Case orders ───────────────────────────────────────────────────────────
    orders = load_year_jsons("case_orders_*.json")
    if orders:
        # Drop known non-case placeholders from case orders.
        excluded_case_numbers = {
            "transcript-instructions",
            "2022-0184",
        }
        before = len(orders)
        orders = [
            o for o in orders
            if str(o.get("case_number", "")).strip().lower() not in excluded_case_numbers
        ]
        removed = before - len(orders)
        if removed:
            print(f"  Removed {removed} non-case order rows")

        override_map = sync_case_type_overrides(orders)
        overridden = 0
        for o in orders:
            if str(o.get("opinion_type", "")).strip().lower() != "case_order":
                continue
            case_number = str(o.get("case_number", "")).strip()
            if case_number in override_map:
                o["case_type"] = override_map[case_number]
                o["_case_type_inference_confidence"] = "manual"
                o["_case_type_inference_reason"] = "manual_override_table"
                overridden += 1
        print(f"  Applied case-type overrides: {overridden}")

        review_rows = [
            {
                "case_number": o.get("case_number"),
                "case_name": o.get("case_name"),
                "term_year": o.get("term_year"),
                "date_issued": o.get("date_issued"),
                "case_type": o.get("case_type"),
                "inference_confidence": o.get("_case_type_inference_confidence"),
                "inference_reason": o.get("_case_type_inference_reason"),
                "rsa_citations": o.get("rsa_citations"),
                "topics": o.get("topics"),
            }
            for o in orders
            if o.get("_case_type_was_null")
            and (
                is_missing(o.get("case_type"))
                or str(o.get("_case_type_inference_confidence", "")).lower() in {"low", "medium", "none"}
            )
        ]
        review_path = PROCESSED_DIR / "case_type_inference_review.csv"
        pd.DataFrame(review_rows).to_csv(review_path, index=False, encoding="utf-8-sig")
        print(f"  Saved review CSV → {review_path} ({len(review_rows)} rows)")

        to_flat_csv(orders, PROCESSED_DIR / "case_orders.csv")
    else:
        print("  No case order records found")

    # ── 3JX orders ────────────────────────────────────────────────────────────
    raw_dir = ROOT / "data" / "raw"
    jx3_records: list[dict] = []
    for jx_path in sorted(raw_dir.glob("3jx_*.json")):
        with open(jx_path, encoding="utf-8") as fh:
            year_recs = json.load(fh)
        if year_recs:
            print(f"  Loaded {len(year_recs)} 3JX records from {jx_path.name}")
            jx3_records.extend(year_recs)
    if jx3_records:
        jx_df = pd.DataFrame(jx3_records)
        # Normalize 3JX records so key display fields are populated.
        if "case_name" in jx_df.columns:
            name_series = jx_df["case_name"].fillna("").astype(str)
            jx_df["case_type"] = name_series.apply(
                lambda n: "criminal"
                if re.match(r"^state\s+of\s+new\s+hampshire\s+v\.\s+", n, flags=re.IGNORECASE)
                else "civil"
            )
        else:
            jx_df["case_type"] = "civil"

        jx_df["outcome"] = "issued"
        jx_df["vote_string"] = "3JX Panel"

        jx_out = PROCESSED_DIR / "3jx_orders.csv"
        jx_df.to_csv(jx_out, index=False, encoding="utf-8-sig")
        print(f"  Saved CSV → {jx_out} ({len(jx_df)} rows)")
    else:
        print("  No 3JX records found — run scrape_3jx.py first")

    print("Done.")


if __name__ == "__main__":
    main()
