"""Build evidence-backed oral-advocate facts from annual archive PDFs.

The archive PDF is parsed independently of transcript metadata.  This is
intentional: metadata is useful for comparison, but must never supply a name,
side, or firm to a court-PDF fact.  The default run creates a small,
deterministic pilot that can be evaluated before the full archive is published.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "processed"
ARCHIVE_ROOT = Path("/Volumes/AI-Storage/nh-supreme-court-transcripts")
DEFAULT_PDF_DIR = ARCHIVE_ROOT / "enrichment" / "user-pages"
DEFAULT_ORAL_ARGUMENTS = ROOT / "data" / "processed" / "oral_arguments.json"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "case_counsel_sample_100.json"
DEFAULT_REPORT = ROOT / "docs" / "case_counsel_sample_100_report.md"
DEFAULT_REVIEW_CSV = ROOT / "data" / "processed" / "case_counsel_sample_100_review.csv"
DEFAULT_MARKDOWN_REVIEW = ROOT / "docs" / "case_counsel_sample_100_review.md"
DEFAULT_SIMPLE_OUTPUT = ROOT / "data" / "processed" / "oral_argument_roster_sample_100.json"
DEFAULT_SIMPLE_REVIEW = ROOT / "docs" / "oral_argument_roster_sample_100_review.md"
FULL_FACTS_OUTPUT = DATA_DIR / "case_counsel.json"
FULL_SIMPLE_OUTPUT = DATA_DIR / "oral_argument_roster.json"
FULL_SIMPLE_REVIEW = ROOT / "docs" / "oral_argument_roster_review.md"
FULL_BRIEF_COUNSEL_OUTPUT = DATA_DIR / "brief_counsel.json"
FULL_COVERAGE_REPORT = ROOT / "docs" / "oral_argument_roster_coverage.md"
FULL_EXCEPTIONS_REPORT = ROOT / "docs" / "oral_argument_roster_exceptions.md"
MANUAL_RECOVERIES_FILE = ROOT / "data" / "oral_argument_roster_manual_recoveries.json"
ROSTER_CORRECTIONS_FILE = ROOT / "data" / "oral_argument_roster_corrections.json"
DEFAULT_OPINIONS = ROOT / "data" / "processed" / "all_opinions.json"
TEXT_DIR = ROOT / "data" / "processed" / "text"
ORAL_TRANSCRIPT_DIR = ROOT / "data" / "processed" / "oral_arguments" / "text"
SOURCE_TYPE = "nh_supreme_court_annual_oral_argument_archive_pdf"
PARSER_VERSION = "case-counsel-pilot-v1"


def surname(value: str) -> str:
    tokens = re.sub(r"[^A-Za-z' -]", " ", value).lower().split()
    return next((token for token in reversed(tokens) if token not in {"jr", "sr", "ii", "iii", "iv", "esq"}), "")


def candidate_names(value: str) -> list[str]:
    value = re.sub(r"\s+", " ", value).strip(" ,")
    if re.search(r"\bmin\.?\b|total|rebuttal|argument|m&o", value, re.IGNORECASE):
        return []
    value = re.sub(r",\s*(?:pro hac vice|senior|assistant|deputy|chief|attorney general|solicitor general).*$", "", value, flags=re.IGNORECASE).strip(" ,")
    names = []
    for part in re.split(r"\s+and\s+", value, flags=re.IGNORECASE):
        part = part.strip(" ,")
        if re.search(r"\b(attorney|general|council|board|department|standards|training|wetlands|compensation|appeal|state|capital|murder|company|corporation|insurance|communications|acquisitions)\b", part, re.IGNORECASE):
            continue
        if len(part.split()) < 2 or part.lower() == "capital murder":
            continue
        if re.search(r"\b[A-Z]\.", part) or re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+", part):
            names.append(part)
    return names


def find_pdf_text_command() -> str:
    command = shutil.which("pdftotext")
    if command:
        return command
    bundled = Path("/Users/greg/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/bin/pdftotext")
    if bundled.exists():
        return str(bundled)
    raise RuntimeError("pdftotext is required to read the saved archive PDFs")


def infer_side(segment: str, position: int) -> tuple[str, str]:
    """Return a side only when the PDF supplies a concrete signal.

    A guessed appellant/appellee side is worse than an explicit unknown; it
    becomes a review item rather than a silent data error.
    """
    separator_match = re.search(r"\bv\.", segment, flags=re.IGNORECASE)
    separator = separator_match.start() if separator_match else None
    if separator is not None and position < separator:
        context = segment[max(0, position - 600) : separator]
    elif separator is not None:
        context = segment[separator : position + 160]
    else:
        context = segment[max(0, position - 600) : position + 160]
    context = context.lower()
    if "attorney general" in context or "state of new hampshire" in context:
        return "state", "high"
    if "appellate defender" in context:
        return "defendant", "high"
    for side in ("petitioner", "respondent", "appellant", "appellee", "plaintiff", "defendant"):
        if re.search(rf"\b{side}\b", context):
            return side, "medium"
    return "unknown", "low"


def infer_firm(segment: str, position: int) -> str:
    separator_match = re.search(r"\bv\.", segment, flags=re.IGNORECASE)
    separator = separator_match.start() if separator_match else None
    if separator is not None and position < separator:
        context = segment[max(0, position - 600) : separator]
    elif separator is not None:
        context = segment[separator : position]
    else:
        context = segment[max(0, position - 600) : position]
    context = context.lower()
    if "attorney general" in context:
        return "NH Attorney General"
    if "appellate defender" in context:
        return "NH Appellate Defender"
    lines = [line.strip() for line in segment[:position].splitlines() if line.strip()]
    if lines:
        firm = re.sub(r"^and\s+", "", lines[-1], flags=re.IGNORECASE)
        if not re.search(r"\b(?:min\.?|total|for|view|video|v\.)\b|\b\d{4}-\d{4}\b", firm, re.IGNORECASE):
            # Annual archives generally render a firm abbreviation on the line
            # immediately before parenthesized counsel.
            if 1 <= len(firm) <= 80 and not re.search(r"\b(?:state of new hampshire|town of|in the matter of)\b", firm, re.IGNORECASE):
                return firm
    return ""


def compact_evidence(segment: str, name: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in segment.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if name.lower() in line.lower() or surname(name) in line.lower():
            evidence = " | ".join(lines[max(0, index - 3) : index + 4])
            return evidence[:700]
    return " | ".join(lines[:8])[:700]


def _looks_like_self_represented(segment: str, position: int) -> bool:
    line_end = segment.find("\n", position)
    local_line = segment[position : line_end if line_end >= 0 else len(segment)]
    return bool(re.search(r"\bfor\s+(?:himself|herself|themselves)\b", local_line, re.IGNORECASE))


def extract_pdf_candidates(pdf_dir: Path) -> dict[str, list[dict[str, str]]]:
    command = find_pdf_text_command()
    rosters: dict[str, list[dict[str, str]]] = {}
    for pdf_path in sorted(pdf_dir.glob("20??.pdf")):
        source_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        with tempfile.NamedTemporaryFile(suffix=".txt") as output:
            subprocess.run([command, "-raw", str(pdf_path), output.name], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            text = Path(output.name).read_text(encoding="utf-8", errors="replace")
        matches = list(re.finditer(r"\b(\d{4}-\d{4})\b", text))
        index = 0
        while index < len(matches):
            # Consecutive docket numbers precede a single consolidated row.
            # Keep them together so each docket receives the row's roster.
            group = [matches[index]]
            next_index = index + 1
            while next_index < len(matches) and not text[group[-1].end() : matches[next_index].start()].strip():
                group.append(matches[next_index])
                next_index += 1
            dockets = [match.group(1) for match in group]
            source_page = text.count("\f", 0, group[0].start()) + 1
            end = matches[next_index].start() if next_index < len(matches) else len(text)
            segment = text[group[0].start() : end]
            found: list[tuple[str, int]] = []
            for name_match in re.finditer(r"\(([^()]{2,160})\)", segment, flags=re.DOTALL):
                found.extend((name, name_match.start()) for name in candidate_names(name_match.group(1)))
            for name_match in re.finditer(r"(?m)^\s*([A-Z][A-Za-z.'’\-]+(?:[ \t]+[A-Z][A-Za-z.'’\-]+){1,5}(?:,[ \t]*(?:Jr\.?|Sr\.?|II|III|IV))?)[ \t]*\n\s*\(\d+\s*min\.", segment):
                found.extend((name, name_match.start()) for name in candidate_names(name_match.group(1)))
            # Some rows keep the unparenthesized attorney and time on one line.
            for name_match in re.finditer(r"(?m)^\s*([A-Z][A-Za-z.'’\-]+(?:[ \t]+[A-Z][A-Za-z.'’\-]+){1,5}(?:,[ \t]*(?:Jr\.?|Sr\.?|II|III|IV))?)[ \t]*\(\d+\s*min\.", segment):
                found.extend((name, name_match.start()) for name in candidate_names(name_match.group(1)))
            # Family and other matters often put the represented party between
            # the attorney name and the allotted-time marker.
            for name_match in re.finditer(r"(?m)^\s*([A-Z][A-Za-z.'’\-]+(?:[ \t]+[A-Z][A-Za-z.'’\-]+){1,5}(?:,[ \t]*(?:Jr\.?|Sr\.?|II|III|IV))?)[ \t]+for\s+[^\n]+\n\s*\(\d+\s*min\.", segment):
                found.extend((name, name_match.start()) for name in candidate_names(name_match.group(1)))
            # Later annual pages often keep the party and time on the same line:
            # "Jane A. Doe for Jane Party (15 min.)".
            for name_match in re.finditer(r"(?m)^\s*([A-Z][A-Za-z.'’\-]+(?:[ \t]+[A-Z][A-Za-z.'’\-]+){1,5}(?:,[ \t]*(?:Jr\.?|Sr\.?|II|III|IV))?)[ \t]+for\s+[^\n]+?\s*\(\d+\s*min\.", segment):
                found.extend((name, name_match.start()) for name in candidate_names(name_match.group(1)))
            # Some multi-party rows state counsel and represented party but put
            # a shared time allotment only after several such entries.
            for name_match in re.finditer(r"(?m)^\s*([A-Z][A-Za-z.'’\-]+(?:[ \t]+[A-Z][A-Za-z.'’\-]+){1,5}(?:,[ \t]*(?:Jr\.?|Sr\.?|II|III|IV))?)[ \t]+for\s+", segment):
                found.extend((name, name_match.start()) for name in candidate_names(name_match.group(1)))
            for docket in dockets:
                seen = {item["attorney_raw"] for item in rosters.get(docket, [])}
                for name, position in found:
                    if name in seen or _looks_like_self_represented(segment, position):
                        continue
                    side, confidence = infer_side(segment, position)
                    rosters.setdefault(docket, []).append({
                        "attorney_raw": name,
                        "firm": infer_firm(segment, position),
                        "side": side,
                        "confidence": confidence,
                        "source_file": pdf_path.name,
                        "source_page": str(source_page),
                        "source_sha256": source_sha256,
                        "source_locator": f"docket row {docket}",
                        "evidence_text": compact_evidence(segment, name),
                    })
                    seen.add(name)
            index = next_index
    return rosters


def load_oral_argument_dockets(path: Path) -> set[str]:
    return {str(item.get("case_number")) for item in json.loads(path.read_text(encoding="utf-8")) if item.get("case_number")}


def load_manual_roster_recoveries() -> dict[str, list[dict[str, str]]]:
    """Load court-roster entries recovered outside the saved annual PDF set."""
    if not MANUAL_RECOVERIES_FILE.exists():
        return {}
    payload = json.loads(MANUAL_RECOVERIES_FILE.read_text(encoding="utf-8"))
    return {str(docket): entries for docket, entries in payload.items() if docket != "comment" and isinstance(entries, list)}


def apply_roster_corrections(candidates: dict[str, list[dict[str, str]]]) -> None:
    """Apply reviewed, source-preserving corrections to parsed roster fields."""
    if not ROSTER_CORRECTIONS_FILE.exists():
        return
    corrections = json.loads(ROSTER_CORRECTIONS_FILE.read_text(encoding="utf-8"))
    remove_names = set(corrections.get("remove_attorney_raw", []))
    split_entries = corrections.get("split_entries", {})
    add_entries = corrections.get("add_entries", {})
    for docket, entries in list(candidates.items()):
        corrected: list[dict[str, str]] = []
        for entry in entries:
            raw_name = str(entry.get("attorney_raw") or "")
            if raw_name in remove_names:
                continue
            replacements = split_entries.get(docket, {}).get(raw_name)
            if replacements:
                for replacement in replacements:
                    replacement_entry = dict(entry)
                    replacement_entry.update(replacement)
                    replacement_entry["confidence"] = "high"
                    replacement_entry["source_locator"] = f"{entry.get('source_locator', '')}; reviewed split"
                    corrected.append(replacement_entry)
                continue
            corrected.append(entry)
        corrected.extend(dict(entry) for entry in add_entries.get(docket, []))
        candidates[docket] = corrected


def add_consolidated_roster_aliases(candidates: dict[str, list[dict[str, str]]], oral_dockets: set[str]) -> None:
    """Attach a shared PDF roster to repository keys that combine dockets."""
    for docket in sorted(oral_dockets):
        components = re.findall(r"20\d{2}-\d{4}", docket)
        if len(components) < 2 or docket in candidates:
            continue
        merged: list[dict[str, str]] = []
        seen = set()
        for component in components:
            for entry in candidates.get(component, []):
                name = entry["attorney_raw"]
                if name in seen:
                    continue
                copied = dict(entry)
                copied["source_locator"] = f"consolidated dockets {', '.join(components)}"
                merged.append(copied)
                seen.add(name)
        if merged:
            candidates[docket] = merged


def _appearance_paragraphs(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines()]
    start = next((index + 1 for index, line in enumerate(lines[:80]) if line.startswith("Opinion Issued:")), None)
    if start is None:
        return []
    body = []
    for line in lines[start:80]:
        if re.match(r"^(?:PER CURIAM|[A-Z][A-Z\-]+(?:\s+[A-Z][A-Z\-]+)?,\s+(?:C\.J\.|J\.))", line):
            break
        body.append(line)
    paragraphs: list[str] = []
    current: list[str] = []
    for line in body:
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(line)
        joined = " ".join(current)
        if re.search(r"\bfor\s+(?:the\s+)?[^.]+\.$", joined, re.IGNORECASE):
            paragraphs.append(joined)
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return [" ".join(part.split()) for part in paragraphs if " for " in part.lower()]


def _person_names(value: str) -> list[str]:
    """Extract attorney-looking names from a small, role-bearing phrase."""
    value = re.sub(r",\s*(?:(?:senior\s+)?(?:assistant\s+)?|deputy\s+|chief\s+)?(?:attorney general|solicitor general).*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:Mr|Ms|Mrs)\.\s+", "", value)
    names = []
    for part in re.split(r"\s+and\s+", value, flags=re.IGNORECASE):
        part = part.strip(" ,()")
        if re.search(r"\b(?:law|office|offices|llp|p\.a\.|attorney|firm|of)\b", part, re.IGNORECASE):
            continue
        if candidate_names(part):
            names.extend(candidate_names(part))
    return list(dict.fromkeys(names))


def parse_official_counsel(docket: str, text: str, source_url: str) -> list[dict[str, str]]:
    """Parse published appearance language into role-specific counsel facts."""
    facts: list[dict[str, str]] = []
    for paragraph in _appearance_paragraphs(text):
        side_match = re.search(r",\s+for\s+(?:the\s+)?(.+?)\.$", paragraph, re.IGNORECASE)
        side = side_match.group(1).strip().lower() if side_match else "unknown"
        known_names: list[str] = []
        for group in re.findall(r"\(([^)]{2,300})\)", paragraph):
            lower = group.lower()
            if "on the brief" not in lower and "orally" not in lower:
                continue
            brief_prefix = re.split(r"\bon the brief(?:s)?\b", group, flags=re.IGNORECASE)[0]
            brief_names = _person_names(brief_prefix)
            known_names.extend(brief_names)
            if "on the brief" in lower:
                for name in brief_names:
                    facts.append({"name": name, "role": "brief_counsel", "side": side})
            if "orally" in lower:
                reference = re.search(r"(?:and|,)\s+(?:Mr|Ms|Mrs)\.\s+([A-Z][A-Za-z'’-]+)\s+orally", group, re.IGNORECASE)
                if reference:
                    oral_names = [name for name in known_names if surname(name) == reference.group(1).lower()]
                else:
                    oral_names = _person_names(re.split(r"\bon the brief(?:s)?\b", group, flags=re.IGNORECASE)[0])
                for name in oral_names:
                    facts.append({"name": name, "role": "oral_advocate", "side": side})
        # Published headers also use: "Dana Alan Curhan ... by brief and orally".
        if re.search(r"\bby brief and orally\b", paragraph, re.IGNORECASE):
            match = re.match(r"([A-Z][A-Za-z.'’\-]+(?:\s+[A-Z][A-Za-z.'’\-]+){1,4})\s*,", paragraph)
            if match:
                for name in _person_names(match.group(1)):
                    facts.extend([
                        {"name": name, "role": "brief_counsel", "side": side},
                        {"name": name, "role": "oral_advocate", "side": side},
                    ])
        # Another common form omits both parentheses and "by":
        # "Christopher M. Johnson, chief appellate defender, ... on the
        # brief and orally, for the defendant."
        if re.search(r"\bon the brief(?:s)? and orally\b", paragraph, re.IGNORECASE) and "(" not in paragraph:
            match = re.match(r"([A-Z][A-Za-z.'’\-]+(?:\s+[A-Z][A-Za-z.'’\-]+){1,4})\s*,", paragraph)
            if match:
                for name in _person_names(match.group(1)):
                    facts.extend([
                        {"name": name, "role": "brief_counsel", "side": side},
                        {"name": name, "role": "oral_advocate", "side": side},
                    ])
    unique = {(item["name"], item["role"], item["side"]): item for item in facts}
    return list(unique.values())


def transcript_confirms_oral_advocate(text: str, attorney_name: str) -> bool:
    """Conservative confirmation for order-only cases without a counsel block."""
    last_name = surname(attorney_name)
    return bool(last_name and re.search(rf"\b(?:mr|ms|mrs)\.?\s+{re.escape(last_name)}\b", text, re.IGNORECASE))


def build_facts(candidates: dict[str, list[dict[str, str]]], dockets: set[str], sample_size: int, opinion_links: dict[str, dict[str, str]] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    selected = sorted(docket for docket in candidates if docket in dockets)[:sample_size]
    facts: list[dict[str, Any]] = []
    for docket in selected:
        for item in candidates[docket]:
            facts.append({
                "docket": docket,
                "attorney_raw": item["attorney_raw"],
                "attorney_canonical": None,
                "role": "scheduled_oral_candidate",
                "side": item["side"],
                "party_label": None,
                "firm": item["firm"] or None,
                "source_type": SOURCE_TYPE,
                "source_file": item["source_file"],
                "source_page": int(item["source_page"]) if str(item.get("source_page") or "").isdigit() else None,
                "source_sha256": item["source_sha256"],
                "source_locator": item["source_locator"],
                "evidence_text": item["evidence_text"],
                "parser_version": PARSER_VERSION,
                "confidence": "medium" if item["confidence"] == "high" else "low",
                "review_status": "needs_review",
            })
        decision = (opinion_links or {}).get(docket)
        text_path = TEXT_DIR / f"{docket}.txt"
        if decision and text_path.exists():
            for item in parse_official_counsel(docket, text_path.read_text(encoding="utf-8"), decision["pdf_url"]):
                facts.append({
                    "docket": docket,
                    "attorney_raw": item["name"],
                    "attorney_canonical": None,
                    "role": item["role"],
                    "side": item["side"],
                    "party_label": None,
                    "firm": None,
                    "source_type": "nh_supreme_court_official_decision",
                    "source_file": decision["pdf_url"],
                    "source_page": 1,
                    "source_sha256": None,
                    "source_locator": "published appearance block",
                    "evidence_text": "Published appearance block",
                    "parser_version": PARSER_VERSION,
                    "confidence": "high",
                    "review_status": "approved",
                })
        # Orders often omit a counsel appearance block. In that circumstance,
        # a transcript naming the scheduled attorney as counsel confirms oral
        # participation without inventing brief counsel.
        transcript_path = ORAL_TRANSCRIPT_DIR / f"{docket}.txt"
        if decision and decision["opinion_type"] == "case_order" and transcript_path.exists():
            transcript = transcript_path.read_text(encoding="utf-8")
            official_oral_surnames = {
                surname(fact["attorney_raw"])
                for fact in facts
                if fact["docket"] == docket and fact["role"] == "oral_advocate"
            }
            for item in candidates[docket]:
                if surname(item["attorney_raw"]) in official_oral_surnames:
                    continue
                if transcript_confirms_oral_advocate(transcript, item["attorney_raw"]):
                    side = item["side"]
                    if side == "unknown" and item["evidence_text"].lstrip().lower().startswith("v."):
                        side = "respondent"
                    facts.append({
                        "docket": docket,
                        "attorney_raw": item["attorney_raw"],
                        "attorney_canonical": None,
                        "role": "oral_advocate",
                        "side": side,
                        "party_label": None,
                        "firm": item["firm"] or None,
                        "source_type": "oral_argument_transcript",
                        "source_file": str(transcript_path.relative_to(ROOT)),
                        "source_page": None,
                        "source_sha256": None,
                        "source_locator": "counsel turn in transcript",
                        "evidence_text": f"Transcript addresses Mr./Ms. {surname(item['attorney_raw']).title()} as counsel.",
                        "parser_version": PARSER_VERSION,
                        "confidence": "high",
                        "review_status": "approved",
                    })
        docket_facts = [fact for fact in facts if fact["docket"] == docket]
        confirmed_surnames = {
            surname(fact["attorney_raw"])
            for fact in docket_facts
            if fact["role"] == "oral_advocate" and fact["review_status"] == "approved"
        }
        for fact in docket_facts:
            if fact["role"] == "scheduled_oral_candidate" and surname(fact["attorney_raw"]) in confirmed_surnames:
                fact["review_status"] = "corroborated"
                fact["confidence"] = "high"
    return facts, selected


def write_report(path: Path, facts: list[dict[str, Any]], selected: list[str], available: int, oral_dockets: set[str]) -> None:
    confidence = Counter(fact["confidence"] for fact in facts)
    status = Counter(fact["review_status"] for fact in facts)
    by_docket: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        by_docket.setdefault(str(fact["docket"]), []).append(fact)
    fully_approved = [docket for docket, docket_facts in by_docket.items() if all(fact["review_status"] == "approved" for fact in docket_facts)]
    publishable_facts = sum(len(by_docket[docket]) for docket in fully_approved)
    missing = sorted(oral_dockets - set(selected))
    lines = [
        "# Case Counsel Pilot — 100-Case Report", "",
        "This report is generated. It records evidence-backed oral-advocate candidates; transcript metadata was not used to populate any fact.", "",
        "## Coverage", "",
        f"- Oral-argument dockets in repository: {len(oral_dockets)}",
        f"- Dockets detected in annual PDFs and eligible for matching: {available}",
        f"- Deterministic pilot dockets selected: {len(selected)}",
        f"- Oral-advocate facts extracted: {len(facts)}",
        f"- Oral-argument dockets outside this pilot: {len(missing)}",
        "", "## Review queue", "",
        f"- Approved high-confidence facts: {status['approved']}",
        f"- Needs review: {status['needs_review']}",
        f"- High confidence: {confidence['high']}; medium: {confidence['medium']}; low: {confidence['low']}",
        f"- Publishable complete rosters: {len(fully_approved)} dockets / {publishable_facts} facts",
        "", "## Next gate", "",
        "Review only the `needs_review` facts, then rerun with a larger sample. Do not publish an unreviewed fact as an attorney-profile count.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_review_csv(path: Path, facts: list[dict[str, Any]]) -> None:
    """Write a spreadsheet-friendly review queue without altering source facts."""
    fieldnames = [
        "review_priority", "review_status", "confidence", "docket", "attorney_raw",
        "role", "side", "firm", "source_file", "source_page", "source_locator",
        "evidence_text", "source_sha256", "recommended_action",
    ]
    rows = []
    for fact in facts:
        needs_review = fact["review_status"] == "needs_review"
        rows.append({
            "review_priority": 1 if needs_review else 2,
            "review_status": fact["review_status"],
            "confidence": fact["confidence"],
            "docket": fact["docket"],
            "attorney_raw": fact["attorney_raw"],
            "role": fact["role"],
            "side": fact["side"],
            "firm": fact["firm"] or "",
            "source_file": fact["source_file"],
            "source_page": fact["source_page"],
            "source_locator": fact["source_locator"],
            "evidence_text": fact["evidence_text"],
            "source_sha256": fact["source_sha256"],
            "recommended_action": "inspect source and set a side or confirm unknown" if needs_review else "spot-check source; no change required",
        })
    rows.sort(key=lambda row: (row["review_priority"], row["docket"], row["attorney_raw"]))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def load_opinion_links(path: Path) -> dict[str, dict[str, str]]:
    """Return one official decision link per docket, including case orders."""
    if not path.exists():
        return {}
    choices: dict[str, dict[str, str]] = {}
    documents = json.loads(path.read_text(encoding="utf-8"))
    for order_path in sorted(DATA_DIR.glob("case_orders_*.json")):
        try:
            documents.extend(json.loads(order_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    for item in documents:
        docket = str(item.get("case_number") or "")
        url = str(item.get("pdf_url") or "")
        if not docket or not url:
            continue
        candidate = {"case_name": str(item.get("case_name") or ""), "pdf_url": url, "opinion_type": str(item.get("opinion_type") or "case_order")}
        current = choices.get(docket)
        if current is None or (candidate["opinion_type"] == "opinion" and current["opinion_type"] != "opinion"):
            choices[docket] = candidate
    return choices


def write_markdown_review(path: Path, facts: list[dict[str, Any]], opinion_links: dict[str, dict[str, str]]) -> None:
    """Write a compact, human-readable docket-level review sheet."""
    by_docket: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        by_docket.setdefault(str(fact["docket"]), []).append(fact)
    needs_review = []
    approved = []
    for docket, docket_facts in sorted(by_docket.items()):
        (needs_review if any(fact["role"] == "scheduled_oral_candidate" and fact["review_status"] == "needs_review" for fact in docket_facts) else approved).append((docket, docket_facts))

    lines = [
        "# Attorney Roster Pilot — Human Review", "",
        "Review the **Needs review** section first. Each row is one docket, not one extracted name. `Unknown` is deliberately unresolved—not an assertion about the party.", "",
        "The **Official decision** link is the repository's matching NH Supreme Court opinion or order. `No linked decision in repository` means the docket did not join to a stored official document; verify against the archive evidence and do not infer a decision link.", "",
        f"Pilot scope: {len(by_docket)} dockets; {len(needs_review)} require review; {len(approved)} have complete high-confidence rosters for spot-checking.",
    ]

    for heading, rows in (("Needs review", needs_review), ("Spot-check approved rosters", approved)):
        lines.extend(["", f"## {heading}", "", "| Docket / case | Confirmed oral advocates | Brief counsel | Unresolved archive candidates | Official decision |", "|---|---|---|---|---|"])
        for docket, docket_facts in rows:
            decision = opinion_links.get(docket)
            if decision:
                title = _markdown_cell(decision["case_name"] or docket)
                docket_cell = f"`{docket}`<br>{title}"
                label = (decision["opinion_type"] or "decision").replace("_", " ").title()
                official = f"[{label}]({decision['pdf_url']})"
            else:
                docket_cell = f"`{docket}`"
                official = "No linked decision in repository"
            advocates = "<br>".join(
                _markdown_cell(f"{fact['attorney_raw']} — {fact['side']}" + (f" ({fact['firm']})" if fact.get("firm") else ""))
                for fact in docket_facts
                if fact["role"] == "oral_advocate"
            )
            briefs = "<br>".join(
                _markdown_cell(f"{fact['attorney_raw']} — {fact['side']}")
                for fact in docket_facts
                if fact["role"] == "brief_counsel"
            )
            archive = "<br>".join(
                _markdown_cell(f"{fact['source_file']} p. {fact['source_page']}: {fact['evidence_text']}")
                for fact in docket_facts
                if fact["role"] == "scheduled_oral_candidate" and fact["review_status"] == "needs_review"
            )
            lines.append(f"| {docket_cell} | {advocates or '—'} | {briefs or '—'} | {archive or '—'} | {official} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_simple_roster_sample(output: Path, review: Path, candidates: dict[str, list[dict[str, str]]], selected: list[str], facts: list[dict[str, Any]], opinion_links: dict[str, dict[str, str]]) -> None:
    """Create the uncomplicated two-source deliverable used for spot checks.

    The PDF roster is deliberately not reconciled against the opinion. It is
    the oral-roster source of truth; published appearance language supplies a
    separate brief-counsel column when available.
    """
    brief_by_docket: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        if fact["role"] == "brief_counsel":
            brief_by_docket.setdefault(str(fact["docket"]), []).append(fact)
    payload_dockets = []
    for docket in selected:
        payload_dockets.append({
            "docket": docket,
            "oral_argument_roster": candidates[docket],
            "brief_counsel": brief_by_docket.get(docket, []),
            "official_decision": opinion_links.get(docket),
        })
    output.write_text(json.dumps({
        "schema_version": "1.0",
        "oral_roster_source": "NH Supreme Court annual oral-argument archive PDFs",
        "brief_counsel_source": "NH Supreme Court official opinions and orders",
        "dockets": payload_dockets,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Annual PDF Oral-Argument Rosters — 100-Case Spot Check", "",
        "The **PDF oral-argument roster** is the source of truth in this sheet. It reports the counsel listed in the annual NH Supreme Court archive, without trying to override it from transcript metadata or an opinion.", "",
        "**Brief counsel** is a separate field from the official decision when the decision has a published appearance block. A dash means no brief counsel was extracted, not that no brief existed.", "",
        "| Docket / case | PDF oral-argument roster | Brief counsel | PDF source | Official decision |",
        "|---|---|---|---|---|",
    ]
    for item in payload_dockets:
        docket = item["docket"]
        decision = item["official_decision"]
        if decision:
            case_cell = f"`{docket}`<br>{_markdown_cell(decision['case_name'] or docket)}"
            decision_label = (decision["opinion_type"] or "decision").replace("_", " ").title()
            decision_cell = f"[{decision_label}]({decision['pdf_url']})"
        else:
            case_cell = f"`{docket}`"
            decision_cell = "No linked decision in repository"
        roster = "<br>".join(_markdown_cell(
            f"{entry['attorney_raw']}" + (f" ({entry['firm']})" if entry.get("firm") else "") + (f" — {entry['side']}" if entry.get("side") != "unknown" else "")
        ) for entry in item["oral_argument_roster"])
        briefs = "<br>".join(_markdown_cell(f"{entry['attorney_raw']} — {entry['side']}") for entry in item["brief_counsel"])
        sources = "<br>".join(_markdown_cell(f"{entry['source_file']} p. {entry['source_page']}") for entry in item["oral_argument_roster"])
        lines.append(f"| {case_cell} | {roster or '—'} | {briefs or '—'} | {sources or '—'} | {decision_cell} |")
    review.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_full_reports(coverage_path: Path, exceptions_path: Path, oral_dockets: set[str], candidates: dict[str, list[dict[str, str]]], selected: list[str]) -> None:
    selected_set = set(selected)
    no_roster = sorted(oral_dockets - selected_set)
    entry_count = sum(len(candidates[docket]) for docket in selected)
    coverage_path.write_text("\n".join([
        "# Annual PDF Oral-Argument Roster Coverage", "",
        "The annual NH Supreme Court archive PDFs are the source of truth for the oral-argument roster. This report tracks coverage, not agreement with transcript metadata.", "",
        f"- Oral-argument dockets in repository: {len(oral_dockets)}",
        f"- Dockets with a parsed annual-PDF roster: {len(selected)}",
        f"- PDF-roster attorney entries: {entry_count}",
        f"- Dockets requiring automated exception triage: {len(no_roster)}",
        "",
        "The exception list contains only dockets for which no annual-PDF roster was detected. Run the exception-triage helper before requesting any manual review.",
    ]) + "\n", encoding="utf-8")
    lines = [
        "# Annual PDF Oral-Argument Roster Exceptions", "",
        "These oral-argument dockets have no detected annual-PDF roster. They need source recovery or targeted review; all other dockets are represented in `oral_argument_roster.json`.", "",
        "| Docket | Reason |", "|---|---|",
    ]
    lines.extend(f"| `{docket}` | No roster parsed from the saved annual PDF archive |" for docket in no_roster)
    exceptions_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--oral-arguments", type=Path, default=DEFAULT_ORAL_ARGUMENTS)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV)
    parser.add_argument("--markdown-review", type=Path, default=DEFAULT_MARKDOWN_REVIEW)
    parser.add_argument("--opinions", type=Path, default=DEFAULT_OPINIONS)
    parser.add_argument("--simple-output", type=Path, default=DEFAULT_SIMPLE_OUTPUT)
    parser.add_argument("--simple-review", type=Path, default=DEFAULT_SIMPLE_REVIEW)
    parser.add_argument("--all", action="store_true", help="Build the full annual-PDF archive instead of the 100-case spot-check.")
    args = parser.parse_args()
    oral_dockets = load_oral_argument_dockets(args.oral_arguments)
    candidates = extract_pdf_candidates(args.pdf_dir)
    candidates.update(load_manual_roster_recoveries())
    apply_roster_corrections(candidates)
    add_consolidated_roster_aliases(candidates, oral_dockets)
    opinion_links = load_opinion_links(args.opinions)
    sample_size = len(candidates) if args.all else args.sample_size
    facts, selected = build_facts(candidates, oral_dockets, sample_size, opinion_links)
    output = FULL_FACTS_OUTPUT if args.all else args.output
    simple_output = FULL_SIMPLE_OUTPUT if args.all else args.simple_output
    simple_review = FULL_SIMPLE_REVIEW if args.all else args.simple_review
    payload = {"schema_version": "1.0", "parser_version": PARSER_VERSION, "sample_size": len(selected), "facts": facts}
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.all:
        brief_facts = [fact for fact in facts if fact["role"] == "brief_counsel"]
        FULL_BRIEF_COUNSEL_OUTPUT.write_text(json.dumps({"schema_version": "1.0", "facts": brief_facts}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        write_full_reports(FULL_COVERAGE_REPORT, FULL_EXCEPTIONS_REPORT, oral_dockets, candidates, selected)
    else:
        write_report(args.report, facts, selected, len(set(candidates) & oral_dockets), oral_dockets)
        write_review_csv(args.review_csv, facts)
        write_markdown_review(args.markdown_review, facts, opinion_links)
    write_simple_roster_sample(simple_output, simple_review, candidates, selected, facts, opinion_links)
    print(f"Wrote {len(facts)} facts for {len(selected)} dockets to {output}")
    if args.all:
        # The full build is intentionally one command: once the PDF roster is
        # written, regenerate profile statistics and replace the preliminary
        # flat exception list with its automated triage.
        subprocess.run([sys.executable, str(ROOT / "scripts" / "extract_attorney_stats.py")], check=True)
        subprocess.run([sys.executable, str(ROOT / "scripts" / "triage_oral_argument_roster_exceptions.py")], check=True)
        print(f"Wrote brief-counsel dataset to {FULL_BRIEF_COUNSEL_OUTPUT}")
        print(f"Wrote coverage report to {FULL_COVERAGE_REPORT}")
        print(f"Wrote exception report to {FULL_EXCEPTIONS_REPORT}")
    print(f"Wrote PDF-roster review sheet to {simple_review}")


if __name__ == "__main__":
    main()
