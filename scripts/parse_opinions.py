"""
scripts/parse_opinions.py
--------------------------
Parse NH Supreme Court opinion PDFs into structured JSON records.
Reads PDFs from data/raw/pdfs/{year}/ and index metadata from data/raw/index_{year}.json.
Outputs: data/processed/opinions_{year}.json

Usage:
    python scripts/parse_opinions.py --years 2024 2025 2026
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("pdfplumber not installed. Run: pip install pdfplumber")
    sys.exit(1)

# ── Path setup (run from project root) ────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.constants import JUSTICE_LAST_NAME_MAP
from utils.vote_parser import parse_vote_block, vote_summary
from utils.dockets import extract_docket_numbers

RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
TEXT_DIR = PROCESSED_DIR / "text"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
TEXT_DIR.mkdir(parents=True, exist_ok=True)

PARSE_VERSION = "1.0.0"

# ── Regex patterns ──────────────────────────────────────────────────────────
CASE_NO_RE = re.compile(r"Case No\.?\s+(\d{4}-\d{4})", re.IGNORECASE)
CITATION_RE = re.compile(
    r"(\d{4})\s+N\.H\.\s+(\d+)", re.IGNORECASE
)
ARGUED_RE = re.compile(r"Argued\s*[:\-]?\s*(.+)", re.IGNORECASE)
ISSUED_RE = re.compile(r"Opinion Issued\s*[:\-]?\s*(.+)", re.IGNORECASE)
# Older opinions print the issuance date as a standalone line below the caption,
# rather than as an "Opinion Issued:" field.  Restrict this match to a complete
# line in the header so dates mentioned in the factual background cannot become
# the decision date.
HEADER_DATE_RE = re.compile(
    r"^\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})\s*$",
    re.MULTILINE,
)
ORDER_ISSUED_RE = re.compile(
    r"the court(?:,\s*|\s+)on\s+(.+?)\s*,?\s*issued",
    re.IGNORECASE | re.DOTALL,
)
ORDER_ON_DATE_RE = re.compile(
    r"\bon\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})\b",
    re.IGNORECASE,
)
ORDER_DATED_RE = re.compile(
    r"\bdated\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})\b",
    re.IGNORECASE,
)
DISTRICT_RE = re.compile(
    r"(?:Superior Court|District Court|Family Court|Probate Court|"
    r"Circuit Court|Administrative|DHHS|DES)\s*[,\-]?\s*(.+?)(?:\n|Case No)",
    re.IGNORECASE,
)
AUTHOR_RE = re.compile(
    r"^(PER CURIAM|([A-Z][A-Z\-]+(?:\s+[A-Z][A-Z\-]+)?),\s+(C\.J\.|J\.))[.\s]",
    re.MULTILINE,
)
OUTCOME_RE = re.compile(
    r"\b(affirm(?:ed)?|reverse(?:d)?|remand(?:ed)?|vacate(?:d)?|dismiss(?:ed)?)\b",
    re.IGNORECASE,
)
RSA_RE = re.compile(
    r"RSA\s+(?:chapter\s+)?\d+[A-Z]?(?:-[A-Z0-9]+)*(?::\d+[A-Z0-9\-]*)?(?:,\s*[IVX]+)?",
    re.IGNORECASE,
)
NOTICE_RE = re.compile(r"NOTICE[:.].*?(?=THE SUPREME COURT|\Z)", re.DOTALL | re.IGNORECASE)
PARAGRAPH_RE = re.compile(r"¶\s*\d+\.?\s*(.+?)(?=¶\s*\d+|$)", re.DOTALL)
LOWER_COURT_JUDGE_RE = re.compile(
    r"(?:Superior Court|Circuit Court|District Court|Family Court|"
    r"Probate Court|Juvenile Court)\s+\(([^)]+?),\s*(?:C\.J\.|J\.)\)",
    re.IGNORECASE,
)

# Topic keyword map — keeps consistent with topic_taxonomy.json
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "criminal": ["criminal", "indictment", "felony", "misdemeanor", "RSA 625", "RSA 626", "RSA 630", "RSA 631", "RSA 632", "RSA 633", "RSA 651"],
    "competency": ["competency", "competent to stand trial", "RSA 135:17", "RSA 135-C", "incompetent"],
    "insurance": ["insurance", "insurer", "insured", "coverage", "liquidation", "RSA 402"],
    "medicaid": ["medicaid", "MCO", "managed care", "RSA 126-A", "DHHS", "managed care organization"],
    "administrative_law": ["administrative", "agency", "certiorari", "RSA 541", "RSA 541-A", "petition for original jurisdiction"],
    "family_law": ["divorce", "parenting", "custody", "RSA 458", "RSA 461-A", "alimony", "termination of parental rights"],
    "civil_procedure": ["summary judgment", "motion to dismiss", "RSA 508", "res judicata"],
    "statutory_interpretation": ["plain meaning", "statutory interpretation", "construe", "legislative intent", "plain language"],
    "constitutional": ["constitutional", "First Amendment", "due process", "equal protection", "Part I Article", "Fourth Amendment"],
    "property": ["property", "easement", "zoning", "RSA 674", "RSA 676"],
    "employment": ["employment", "workers compensation", "RSA 281", "wrongful termination"],
    "contract": ["contract", "breach", "damages", "warranty"],
    "tort": ["negligence", "liability", "personal injury", "medical malpractice"],
    "evidence": ["hearsay", "admissibility", "expert witness", "privilege"],
    "DWI": ["DWI", "DUI", "implied consent", "RSA 265-A", "blood alcohol"],
    "domestic_violence": ["domestic violence", "protective order", "RSA 173-B", "stalking"],
    "tax": ["tax", "RSA 76", "RSA 77", "RSA 78", "assessment", "abatement"],
}

STANDARD_OF_REVIEW_KEYWORDS = {
    "de_novo": ["de novo", "fresh eyes", "no deference"],
    "abuse_of_discretion": ["abuse of discretion"],
    "clear_error": ["clear error", "clearly erroneous"],
    "substantial_evidence": ["substantial evidence"],
    "plain_error": ["plain error"],
}

LOWER_COURT_TYPES = {
    "superior court": "superior_court",
    "district court": "district_court",
    "family court": "family_court",
    "probate court": "probate_court",
    "circuit court": "circuit_court",
    "dhhs": "administrative",
    "des": "administrative",
    "puc": "administrative",
    "labor": "administrative",
}


def extract_text(pdf_path: Path, max_pages: int | None = None) -> str:
    """Extract text from a PDF using pdfplumber, optionally limiting page count."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_iter = pdf.pages[:max_pages] if max_pages else pdf.pages
            pages = [page.extract_text() or "" for page in page_iter]
        return "\n".join(pages)
    except Exception as exc:
        print(f"    PDF extraction error {pdf_path.name}: {exc}")
        return ""


def strip_notice(text: str) -> str:
    """Remove the NOTICE preamble block."""
    cleaned = NOTICE_RE.sub("", text)
    return cleaned.strip()


def parse_date(raw: str | None) -> str | None:
    """Try to parse various date formats to ISO YYYY-MM-DD."""
    if not raw:
        return None
    raw = re.sub(r"\s+", " ", str(raw)).strip().rstrip(".,;:")
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%B %d %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return raw  # return raw if unparseable


def extract_opinion_header_date(text: str) -> str | None:
    """Return the standalone issuance date printed in an opinion header."""
    # Opinion headers occur before counsel names and the opinion text.  Keeping
    # this window small avoids treating a historical date from the facts as the
    # issuance date.
    match = HEADER_DATE_RE.search(text[:800])
    return parse_date(match.group(1)) if match else None


def extract_case_order_date(text: str) -> str | None:
    """Extract case order issue dates from order PDF text."""
    collapsed = re.sub(r"\s+", " ", text[:2400])
    m = ORDER_ISSUED_RE.search(collapsed)
    if m:
        parsed = parse_date(m.group(1).strip())
        if parsed:
            return parsed

    # Fallback patterns used by some older order templates.
    for pat in (ORDER_DATED_RE, ORDER_ON_DATE_RE):
        m2 = pat.search(collapsed)
        if not m2:
            continue
        parsed = parse_date(m2.group(1).strip())
        if parsed:
            return parsed

    return None


def detect_topics(text: str) -> list[str]:
    text_lower = text.lower()
    found = []
    for topic, kws in TOPIC_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in kws):
            found.append(topic)
    return found


def detect_standard_of_review(text: str) -> list[str]:
    text_lower = text.lower()
    return [k for k, kws in STANDARD_OF_REVIEW_KEYWORDS.items()
            if any(kw in text_lower for kw in kws)]


def derive_case_type(topics: list[str]) -> str | None:
    """Derive broad case type from detected topics."""
    if not topics:
        return None
    topic_set = set(topics)
    if "family_law" in topic_set or "domestic_violence" in topic_set:
        return "family/domestic"
    if "criminal" in topic_set:
        return "criminal"
    return "civil"


def extract_rsa_citations(text: str) -> list[str]:
    raw = RSA_RE.findall(text)
    # Normalize whitespace
    normalized = []
    for r in raw:
        cleaned = re.sub(r"\s+", " ", r.strip())
        m = re.match(r"RSA\s+chapter\s+(.+)$", cleaned, flags=re.IGNORECASE)
        if m:
            cleaned = f"RSA {m.group(1).strip()}"
        normalized.append(cleaned)
    return list(dict.fromkeys(normalized))  # deduplicate, preserve order


def extract_outcome(text: str) -> str | None:
    """Find the primary outcome verb in the conclusion."""
    tail = text[-2000:] if len(text) > 2000 else text
    # Weight matches near "we affirm/reverse/remand"
    we_re = re.compile(
        r"\bwe\s+(affirm|reverse|remand|vacate|dismiss)\b", re.IGNORECASE
    )
    m = we_re.search(tail)
    if m:
        verb = m.group(1).lower()
        # Check for "reverse and remand"
        context = tail[m.start():m.start()+60]
        if "reverse" in verb and "remand" in context.lower():
            return "reversed_and_remanded"
        if "affirm" in verb and "remand" in context.lower():
            return "affirmed_and_remanded"
        mapping = {
            "affirm": "affirmed",
            "reverse": "reversed",
            "remand": "remanded",
            "vacate": "vacated",
            "dismiss": "dismissed",
        }
        return mapping.get(verb, verb + "ed")
    # Fallback — scan full tail
    for m2 in OUTCOME_RE.finditer(tail):
        token = m2.group(1).lower()
        if token.startswith("affirm"):
            return "affirmed"
        if token.startswith("reverse"):
            return "reversed"
        if token.startswith("remand"):
            return "remanded"
        if token.startswith("vacat"):
            return "vacated"
        if token.startswith("dismiss"):
            return "dismissed"
    return None


def extract_author(text: str) -> str:
    """Return justice key for opinion author, or 'per_curiam'."""
    # Look in the first ~2000 chars (after header) and last 500 chars
    search_zone = text[:3000]
    m = AUTHOR_RE.search(search_zone)
    if not m:
        return "per_curiam"
    if m.group(1).startswith("PER CURIAM"):
        return "per_curiam"
    last_name = m.group(2).upper()
    return JUSTICE_LAST_NAME_MAP.get(last_name, "per_curiam")


# Patterns that mark the end of a lower court name (case numbers, citation labels, etc.)
_LC_STOP_RE = re.compile(
    r"Case\s*No\.?|Citation\s*:|Order\s*No\.?|\bNo\.\s*\d{4}|\d{4}-\d{4}",
    re.IGNORECASE,
)
# Matches a judge-name parenthetical like "(Smith, J.)" or "(Jones, C.J.)"
_LC_JUDGE_PAREN_RE = re.compile(r"\([A-Za-z\s''\u2018\u2019-]+,\s*(?:C\.J\.|J\.)\)")


def _clean_lower_court_snippet(snippet: str) -> str | None:
    """Trim noise from a raw lower-court header snippet."""
    # Stop at the first single newline
    snippet = snippet.split("\n")[0]
    # Stop at case-number / citation markers
    m = _LC_STOP_RE.search(snippet)
    if m:
        snippet = snippet[: m.start()]
    # If there's a judge parenthetical "(Smith, J.)", end the string there
    m_judge = _LC_JUDGE_PAREN_RE.search(snippet)
    if m_judge:
        snippet = snippet[: m_judge.end()]
    snippet = re.sub(r"\s+", " ", snippet).strip().rstrip(" ,;-")
    # Drop sentence-fragment leads
    snippet = re.sub(r"^(?:the\s+|l\s+in\s+|in\s+)", "", snippet, flags=re.IGNORECASE)
    # Discard if no "court" reference (captured garbage mid-text)
    if snippet and "court" not in snippet.lower():
        return None
    return snippet or None


def extract_lower_court(text: str) -> tuple[str | None, str | None]:
    """Return (raw lower court string, normalized type)."""
    header = text[:800]
    for raw_key, norm_key in LOWER_COURT_TYPES.items():
        idx = header.lower().find(raw_key)
        if idx != -1:
            snippet = header[idx: idx + 150].strip()
            return _clean_lower_court_snippet(snippet), norm_key
    return None, None


def extract_lower_court_judge(text: str) -> str | None:
    """Extract the presiding lower court judge name from text like 'Superior Court (Smith, J.)'."""
    search_zone = text[:2500]
    m = LOWER_COURT_JUDGE_RE.search(search_zone)
    return m.group(1).strip() if m else None


def get_summary_paragraph(text: str) -> str:
    """Return the first substantive paragraph (¶1 or ¶2)."""
    # Try numbered paragraphs
    matches = PARAGRAPH_RE.findall(text)
    if matches:
        para = matches[0].strip()[:600]
        return clean_summary_text(para)

    # Fallback: find author byline, then take next paragraph
    m = AUTHOR_RE.search(text)
    if m:
        after = text[m.end():m.end() + 800].strip()
        lines = [l.strip() for l in after.split("\n") if l.strip()]
        if lines:
            return clean_summary_text(" ".join(lines[:4])[:600])

    return ""


def clean_summary_text(value: str) -> str:
    cleaned = value.replace("\ufffd", "").strip()
    cleaned = re.sub(r"^\s*[][(){}\"'“”‘’`]+\s*", "", cleaned)
    cleaned = re.sub(r"\s*[][(){}\"'“”‘’`]+\s*$", "", cleaned)
    return cleaned.strip()


def parse_pdf(pdf_path: Path, meta: dict) -> dict:
    """Parse a single opinion PDF into a structured record."""
    # Case orders generally include date/outcome in the opening pages.
    max_pages = 3 if str(meta.get("opinion_type", "")).strip().lower() == "case_order" else None
    text = extract_text(pdf_path, max_pages=max_pages)
    if not text:
        return {}

    clean_text = strip_notice(text)

    # ── Case number ──────────────────────────────────────────────────────────
    source_file_key = str(meta.get("case_number") or pdf_path.stem)
    case_number = meta.get("case_number")
    if not case_number:
        m = CASE_NO_RE.search(clean_text)
        case_number = m.group(1) if m else pdf_path.stem
    docket_numbers = extract_docket_numbers(clean_text[:1800])
    if not docket_numbers:
        docket_numbers = extract_docket_numbers(case_number)

    # ── Citation ──────────────────────────────────────────────────────────────
    citation_year, citation_seq, citation = None, None, None
    cm = CITATION_RE.search(clean_text)
    if cm:
        citation_year = int(cm.group(1))
        citation_seq = int(cm.group(2))
        citation = f"{citation_year} N.H. {citation_seq}"

    # ── Dates ─────────────────────────────────────────────────────────────────
    date_argued = None
    am = ARGUED_RE.search(clean_text[:800])
    if am:
        date_argued = parse_date(am.group(1))

    date_issued = extract_opinion_header_date(clean_text)
    if not date_issued:
        im = ISSUED_RE.search(clean_text[:800])
        if im:
            date_issued = parse_date(im.group(1))
    if not date_issued:
        date_issued = parse_date(meta.get("date_issued"))

    if not date_issued:
        date_issued = extract_case_order_date(clean_text)

    days_to_decision = None
    if date_argued and date_issued:
        try:
            d1 = datetime.fromisoformat(date_argued)
            d2 = datetime.fromisoformat(date_issued)
            days_to_decision = (d2 - d1).days
        except ValueError:
            pass

    try:
        term_year = citation_year or (int(date_issued[:4]) if date_issued else None) or meta.get("year")
    except (ValueError, TypeError):
        term_year = meta.get("year")

    # ── Author ────────────────────────────────────────────────────────────────
    author_key = extract_author(clean_text)

    # ── Votes ─────────────────────────────────────────────────────────────────
    votes = parse_vote_block(clean_text, author_key, bench_date=date_argued or date_issued)
    vsummary = vote_summary(votes)

    # ── Lower court ───────────────────────────────────────────────────────────
    lower_court_raw, lower_court_type = extract_lower_court(clean_text)
    lower_court_judge = extract_lower_court_judge(clean_text)

    # ── Outcome ───────────────────────────────────────────────────────────────
    outcome = extract_outcome(clean_text)

    # ── Topics ────────────────────────────────────────────────────────────────
    topics = detect_topics(clean_text)

    # ── RSA citations ─────────────────────────────────────────────────────────
    rsa_citations = extract_rsa_citations(clean_text)
    rsa_primary = rsa_citations[0] if rsa_citations else None

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = get_summary_paragraph(clean_text)

    # ── Standards of review ───────────────────────────────────────────────────
    standards = detect_standard_of_review(clean_text)

    # ── Word count ────────────────────────────────────────────────────────────
    word_count = len(clean_text.split())

    # Save full text
    text_path = TEXT_DIR / f"{case_number}.txt"
    text_path.write_text(clean_text, encoding="utf-8")

    return {
        "case_number": case_number,
        "source_file_key": source_file_key,
        "docket_numbers": docket_numbers,
        "citation": citation,
        "citation_year": citation_year,
        "citation_seq": citation_seq,
        "case_name": meta.get("case_name", ""),
        "pdf_url": meta.get("pdf_url", ""),
        "pdf_local_path": str(pdf_path),
        "date_argued": date_argued,
        "date_issued": date_issued,
        "days_to_decision": days_to_decision,
        "term_year": term_year,
        "lower_court": lower_court_raw,
        "lower_court_type": lower_court_type,
        "lower_court_judge": lower_court_judge,
        "case_type": derive_case_type(topics),
        "appeal_type": "standard",
        "outcome": outcome,
        "author": author_key,
        "author_display": "Per Curiam" if author_key == "per_curiam"
            else f"{author_key.replace('_', ' ').title()}, J.",
        "votes": votes,
        **{k: vsummary[k] for k in vsummary},
        "topics": topics,
        "rsa_citations": rsa_citations,
        "rsa_primary": rsa_primary,
        "involves_statutory_interpretation": "statutory_interpretation" in topics,
        "standard_of_review": standards,
        "summary_paragraph": summary,
        "word_count": word_count,
        "opinion_type": meta.get("opinion_type", "opinion"),
        "parse_version": PARSE_VERSION,
        "parse_timestamp": datetime.utcnow().isoformat(),
        "parse_confidence": 0.8,
        "manual_override": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Parse NH Supreme Court opinion PDFs")
    parser.add_argument("--years", nargs="+", type=int, default=[2024, 2025, 2026])
    parser.add_argument(
        "--source",
        choices=["opinions", "orders"],
        default="opinions",
        help="'opinions' reads index_{year}.json (default); 'orders' reads orders_index_{year}.json",
    )
    args = parser.parse_args()

    source = args.source

    for year in args.years:
        print(f"\n=== Parsing {year} ({source}) ===")

        if source == "orders":
            index_path = RAW_DIR / f"orders_index_{year}.json"
            pdf_base_dir = RAW_DIR / "pdfs" / "orders" / str(year)
            scraper_hint = "scrape_orders_index.py"
        else:
            index_path = RAW_DIR / f"index_{year}.json"
            pdf_base_dir = RAW_DIR / "pdfs" / str(year)
            scraper_hint = "scrape_index.py"

        if not index_path.exists():
            print(f"  No index for {year} — run {scraper_hint} first")
            continue

        with open(index_path, encoding="utf-8") as fh:
            index = json.load(fh)

        opinion_records = []
        order_records = []

        for meta in index:
            local_path = meta.get("pdf_local_path")
            if not local_path:
                # Try to infer from URL basename
                from urllib.parse import urlparse
                pdf_url = meta.get("pdf_url", "")
                url_basename = Path(urlparse(pdf_url).path).name if pdf_url else ""
                if url_basename:
                    possible = pdf_base_dir / url_basename
                    if possible.exists():
                        local_path = str(possible)
                # Also try case_number as fallback
                if not local_path:
                    cn = meta.get("case_number", "")
                    if cn:
                        possible2 = pdf_base_dir / f"{cn}.pdf"
                        if possible2.exists():
                            local_path = str(possible2)
                if not local_path:
                    print(f"  No local PDF for {meta.get('case_name', 'unknown')} — skipped")
                    continue

            pdf_path = Path(local_path)
            if not pdf_path.exists():
                print(f"  Missing {pdf_path} — skipped")
                continue

            print(f"  Parsing {pdf_path.name} …")
            rec = parse_pdf(pdf_path, meta)
            if not rec:
                continue

            if meta.get("opinion_type") == "case_order":
                order_records.append(rec)
            else:
                opinion_records.append(rec)

        # Save
        if source == "orders":
            # All records go to case_orders_{year}.json
            ord_path = PROCESSED_DIR / f"case_orders_{year}.json"
            all_order_recs = order_records + opinion_records  # opinion_type field handles labeling
            with open(ord_path, "w", encoding="utf-8") as fh:
                json.dump(all_order_recs, fh, indent=2, ensure_ascii=False)
            print(f"  Saved {len(all_order_recs)} case orders → {ord_path}")
        else:
            op_path = PROCESSED_DIR / f"opinions_{year}.json"
            with open(op_path, "w", encoding="utf-8") as fh:
                json.dump(opinion_records, fh, indent=2, ensure_ascii=False)
            print(f"  Saved {len(opinion_records)} opinions → {op_path}")

            if order_records:
                ord_path = PROCESSED_DIR / f"case_orders_{year}.json"
                with open(ord_path, "w", encoding="utf-8") as fh:
                    json.dump(order_records, fh, indent=2, ensure_ascii=False)
                print(f"  Saved {len(order_records)} case orders → {ord_path}")


if __name__ == "__main__":
    main()
