"""
Citation extraction and resolution for NH Supreme Court opinions.
Supports NH, federal, and other state court citations.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

# NH Reporter citation pattern: "124 N.H. 226"
NH_REPORTER_RE = re.compile(
    r"\b(\d+)\s+N\.?H\.?\s+(\d+)\b",
    re.IGNORECASE
)

# Neutral citation pattern: "2020 NH 012" or "2020-NH-012"
NH_NEUTRAL_RE = re.compile(
    r"\b(20\d{2})[\s\-]NH[\s\-](\d+)\b",
    re.IGNORECASE
)

# Federal citations
US_SUPREME_COURT_RE = re.compile(
    r"\b(\d+)\s+U\.?S\.?\s+(\d+)",
    re.IGNORECASE
)

FEDERAL_CIRCUIT_RE = re.compile(
    r"\b(\d+)\s+F\.?(?:3d|2d|App'?\.?\s*(?:\(?2d?\)?|3d?)?)\s+(\d+)",
    re.IGNORECASE
)

FEDERAL_DISTRICT_RE = re.compile(
    r"\b(\d+)\s+F\.?Supp\.?(?:\s*(?:2d|3d))?\s+(\d+)",
    re.IGNORECASE
)

# Other state reporter patterns
STATE_REPORTER_RE = re.compile(
    r"\b(\d+)\s+(?:A\.?3d?|So\.?(?:2d|3d)?|N\.?E\.?2?d?|N\.?W\.?2?d?|P\.?2?3?d?|S\.?E\.?2?d?|S\.?W\.?2?d?|N\.?Y\.?S\.?2?d?|Cal\.?Rptr\.?2?d?|Pac\.?2?d?|Atl\.?2?d?|So\.?2?d?|N\.?E\.?2?d?|N\.?W\.?2?d?)\s+(\d+)\b",
    re.IGNORECASE
)

# Parenthetical year pattern for context
YEAR_PAREN_RE = re.compile(r"\((\d{4})\)")


class Citation:
    """Represents an extracted citation."""
    
    def __init__(
        self,
        text: str,
        citation_type: str,
        volume: Optional[str] = None,
        page: Optional[str] = None,
        year: Optional[int] = None,
        sequence: Optional[int] = None,
        start_pos: int = 0,
        end_pos: int = 0,
    ):
        self.text = text
        self.citation_type = citation_type  # "reporter" or "neutral"
        self.volume = volume
        self.page = page
        self.year = year
        self.sequence = sequence
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.resolved_case_number: Optional[str] = None
        self.confidence: str = "unknown"  # "high", "medium", "low", "unknown"
    
    def __repr__(self) -> str:
        return f"Citation({self.text}, type={self.citation_type}, resolved={self.resolved_case_number})"
    
    def to_dict(self) -> dict:
        """Convert citation to dictionary for serialization."""
        return {
            "text": self.text,
            "type": self.citation_type,
            "volume": self.volume,
            "page": self.page,
            "year": self.year,
            "sequence": self.sequence,
            "resolved_case_number": self.resolved_case_number,
            "confidence": self.confidence,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
        }


def extract_citations(text: str) -> list[Citation]:
    """
    Extract all case citations from opinion text.
    
    Returns list of Citation objects with position information.
    """
    citations = []
    
    # Extract NH Reporter citations
    for match in NH_REPORTER_RE.finditer(text):
        volume = match.group(1)
        page = match.group(2)
        
        # Look for year in nearby parentheses
        year = None
        context_start = max(0, match.start() - 50)
        context_end = min(len(text), match.end() + 20)
        context = text[context_start:context_end]
        year_match = YEAR_PAREN_RE.search(context)
        if year_match:
            year = int(year_match.group(1))
        
        citation = Citation(
            text=match.group(0),
            citation_type="nh_reporter",
            volume=volume,
            page=page,
            year=year,
            start_pos=match.start(),
            end_pos=match.end(),
        )
        citations.append(citation)
    
    # Extract NH neutral citations
    for match in NH_NEUTRAL_RE.finditer(text):
        year = int(match.group(1))
        sequence = int(match.group(2))

        citation = Citation(
            text=match.group(0),
            citation_type="nh_neutral",
            year=year,
            sequence=sequence,
            start_pos=match.start(),
            end_pos=match.end(),
        )
        citations.append(citation)

    # Extract US Supreme Court citations
    for match in US_SUPREME_COURT_RE.finditer(text):
        volume = match.group(1)
        page = match.group(2)

        year = None
        context_start = max(0, match.start() - 50)
        context_end = min(len(text), match.end() + 20)
        context = text[context_start:context_end]
        year_match = YEAR_PAREN_RE.search(context)
        if year_match:
            year = int(year_match.group(1))

        citation = Citation(
            text=match.group(0),
            citation_type="us_supreme",
            volume=volume,
            page=page,
            year=year,
            start_pos=match.start(),
            end_pos=match.end(),
        )
        citations.append(citation)

    # Extract Federal Circuit citations
    for match in FEDERAL_CIRCUIT_RE.finditer(text):
        volume = match.group(1)
        page = match.group(2)

        year = None
        context_start = max(0, match.start() - 50)
        context_end = min(len(text), match.end() + 20)
        context = text[context_start:context_end]
        year_match = YEAR_PAREN_RE.search(context)
        if year_match:
            year = int(year_match.group(1))

        citation = Citation(
            text=match.group(0),
            citation_type="federal_circuit",
            volume=volume,
            page=page,
            year=year,
            start_pos=match.start(),
            end_pos=match.end(),
        )
        citations.append(citation)

    # Extract Federal District citations
    for match in FEDERAL_DISTRICT_RE.finditer(text):
        volume = match.group(1)
        page = match.group(2)

        year = None
        context_start = max(0, match.start() - 50)
        context_end = min(len(text), match.end() + 20)
        context = text[context_start:context_end]
        year_match = YEAR_PAREN_RE.search(context)
        if year_match:
            year = int(year_match.group(1))

        citation = Citation(
            text=match.group(0),
            citation_type="federal_district",
            volume=volume,
            page=page,
            year=year,
            start_pos=match.start(),
            end_pos=match.end(),
        )
        citations.append(citation)

    # Extract Other State Reporter citations
    for match in STATE_REPORTER_RE.finditer(text):
        volume = match.group(1)
        page = match.group(2)

        year = None
        context_start = max(0, match.start() - 50)
        context_end = min(len(text), match.end() + 20)
        context = text[context_start:context_end]
        year_match = YEAR_PAREN_RE.search(context)
        if year_match:
            year = int(year_match.group(1))

        citation = Citation(
            text=match.group(0),
            citation_type="other_state",
            volume=volume,
            page=page,
            year=year,
            start_pos=match.start(),
            end_pos=match.end(),
        )
        citations.append(citation)

    # Sort by position and deduplicate overlapping citations
    citations.sort(key=lambda c: c.start_pos)

    return citations


def resolve_citation(citation: Citation, opinions_index: dict) -> bool:
    """
    Resolve a citation to a case number using the opinions index.
    
    Args:
        citation: Citation object to resolve
        opinions_index: Dict mapping citation strings or case identifiers to case_number
    
    Returns:
        True if resolved, False otherwise. Updates citation.resolved_case_number and confidence.
    """
    if citation.citation_type in {"nh_neutral", "neutral"}:
        # Try neutral format: year + sequence
        if citation.year and citation.sequence:
            # Format: YYYY-SSSS (zero-padded sequence)
            case_number = f"{citation.year}-{citation.sequence:04d}"
            
            if case_number in opinions_index:
                citation.resolved_case_number = case_number
                citation.confidence = "high"
                return True
            
            # Try without zero-padding
            case_number_alt = f"{citation.year}-{citation.sequence}"
            if case_number_alt in opinions_index:
                citation.resolved_case_number = case_number_alt
                citation.confidence = "high"
                return True
    
    elif citation.citation_type in {"nh_reporter", "reporter"}:
        # Try reporter citation lookup: volume + page
        reporter_key = f"{citation.volume} N.H. {citation.page}"
        
        if reporter_key in opinions_index:
            citation.resolved_case_number = opinions_index[reporter_key]
            citation.confidence = "high"
            return True
        
        # If year is available, narrow search
        if citation.year:
            year_key = f"{citation.year}:{reporter_key}"
            if year_key in opinions_index:
                citation.resolved_case_number = opinions_index[year_key]
                citation.confidence = "high"
                return True
    
    # Federal and other state citations are extracted but not resolved to NH case numbers
    # They remain as external citations
    citation.confidence = "unresolved"
    return False


def build_citation_index(opinions_df) -> dict:
    """
    Build an index mapping citation strings to case numbers.
    
    Args:
        opinions_df: DataFrame with opinion metadata including citation and case_number
    
    Returns:
        Dict mapping citation strings (various formats) to case_number
    """
    index = {}
    
    for _, row in opinions_df.iterrows():
        case_number = row.get("case_number")
        if not case_number:
            continue
        
        # Index by case_number itself (for neutral citations)
        index[case_number] = case_number
        
        # Index by citation if available
        citation = row.get("citation")
        if citation and isinstance(citation, str):
            index[citation.strip()] = case_number
            
            # Also index normalized version
            citation_normalized = citation.replace("  ", " ").strip()
            index[citation_normalized] = case_number
        
        # Index by year:citation for disambiguation
        year = row.get("citation_year")
        if pd.notna(year) and citation:
            year_key = f"{int(year)}:{citation}"
            index[year_key] = case_number
    
    return index


def extract_and_resolve_citations(
    text: str,
    opinions_index: dict,
) -> tuple[list[Citation], list[Citation]]:
    """
    Extract citations from text and resolve them to case numbers.
    
    Returns:
        Tuple of (resolved_citations, unresolved_citations)
    """
    citations = extract_citations(text)
    
    resolved = []
    unresolved = []
    
    for citation in citations:
        if resolve_citation(citation, opinions_index):
            resolved.append(citation)
        else:
            unresolved.append(citation)
    
    return resolved, unresolved


def deduplicate_citations(citations: list[Citation]) -> list[Citation]:
    """
    Remove duplicate citations pointing to the same case.
    Keeps the citation with highest confidence.
    """
    by_case = {}
    
    for citation in citations:
        if not citation.resolved_case_number:
            continue
        
        case_num = citation.resolved_case_number
        
        if case_num not in by_case:
            by_case[case_num] = citation
        else:
            # Keep highest confidence
            existing = by_case[case_num]
            confidence_order = {"high": 3, "medium": 2, "low": 1, "unknown": 0, "unresolved": 0}
            
            if confidence_order.get(citation.confidence, 0) > confidence_order.get(existing.confidence, 0):
                by_case[case_num] = citation
    
    return list(by_case.values())
