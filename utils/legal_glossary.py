"""Plain-language definitions for common appellate terms."""

from __future__ import annotations

import re
import html


NH_LEGAL_GLOSSARY = {
    "Affirmed": "The appellate court agreed with the result reached below.",
    "Reversed": "The appellate court overturned all or part of the decision below.",
    "Remanded": "The case was sent back for additional proceedings.",
    "Vacated": "The earlier judgment or order was set aside.",
    "Per Curiam": "An opinion issued in the court's name without a named author.",
    "Writ of Certiorari": "A request that a higher court review a lower tribunal's decision.",
    "En Banc": "A hearing before the full court rather than a smaller panel.",
    "Habeas Corpus": "A proceeding testing whether a person's detention is lawful.",
    "Injunction": "A court order requiring or prohibiting specified conduct.",
    "Mandamus": "An extraordinary order directing a public official or tribunal to perform a duty.",
    "Stare Decisis": "The practice of following controlling precedent.",
    "Amicus Curiae": "A nonparty who offers information or argument to assist the court.",
    "De Novo": "Fresh review without deference to the earlier legal conclusion.",
    "Res Judicata": "A final judgment bars the same parties from relitigating the same claim.",
    "Collateral Estoppel": "A decided issue cannot ordinarily be relitigated by the same parties.",
    "Standard of Review": "The level of deference an appellate court gives the decision below.",
    "Harmless Error": "An error that did not affect the result enough to require relief.",
    "Standing": "The requirement that a party have a sufficient stake in the dispute.",
    "Moot": "No longer presenting a live dispute the court can resolve.",
    "Dicta": "Language in an opinion that was not necessary to decide the case.",
    "Holding": "The legal rule necessary to the court's disposition of the case.",
}


def get_definition(term: str) -> str | None:
    normalized = str(term or "").strip().casefold()
    for key, definition in NH_LEGAL_GLOSSARY.items():
        if key.casefold() == normalized:
            return definition
    return None


def find_terms(text: str) -> list[dict[str, str]]:
    """Return glossary terms appearing in text, longest terms first."""
    found = []
    for term in sorted(NH_LEGAL_GLOSSARY, key=len, reverse=True):
        if re.search(rf"\b{re.escape(term)}\b", text or "", re.IGNORECASE):
            found.append({"term": term, "definition": NH_LEGAL_GLOSSARY[term]})
    return found


def annotate_terms_html(text: str) -> str:
    """Return escaped text with inline, hoverable plain-English definitions."""
    source = str(text or "")
    if not source:
        return ""
    terms = sorted(NH_LEGAL_GLOSSARY, key=len, reverse=True)
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(term) for term in terms) + r")\b",
        re.IGNORECASE,
    )
    chunks: list[str] = []
    cursor = 0
    for match in pattern.finditer(source):
        chunks.append(html.escape(source[cursor : match.start()]))
        definition = get_definition(match.group(0)) or ""
        chunks.append(
            '<abbr class="legal-term" title="'
            + html.escape(definition, quote=True)
            + '">'
            + html.escape(match.group(0))
            + "</abbr>"
        )
        cursor = match.end()
    chunks.append(html.escape(source[cursor:]))
    return "".join(chunks)
