"""
Tests for utils/citations.py
"""

from __future__ import annotations

import pytest

from utils.citations import (
    extract_citations,
    resolve_citation,
    build_citation_index,
    deduplicate_citations,
    Citation,
)


class TestCitationExtraction:
    """Tests for citation extraction from text."""

    def test_extract_reporter_citation(self):
        """Test extraction of NH Reporter citations."""
        text = "In State v. Ball, 124 N.H. 226 (1983), we held..."
        
        citations = extract_citations(text)
        
        assert len(citations) > 0
        assert any(c.volume == "124" and c.page == "226" for c in citations)

    def test_extract_neutral_citation(self):
        """Test extraction of neutral citations."""
        text = "See 2020 NH 012 for more details."
        
        citations = extract_citations(text)
        
        assert len(citations) > 0
        assert any(c.year == 2020 and c.sequence == 12 for c in citations)

    def test_extract_multiple_citations(self, sample_citation_text):
        """Test extraction of multiple citations from text."""
        citations = extract_citations(sample_citation_text)
        
        assert len(citations) >= 3  # Should find at least 3 citations

    def test_extract_citation_with_year(self):
        """Test that year is extracted from parenthetical context."""
        text = "State v. Smith, 170 N.H. 186 (2017)"
        
        citations = extract_citations(text)
        
        assert len(citations) > 0
        assert citations[0].year == 2017

    def test_extract_handles_variations(self):
        """Test extraction handles citation format variations."""
        text = "124 N.H. 226 and also 124 NH 227"
        
        citations = extract_citations(text)
        
        assert len(citations) == 2


class TestCitationResolution:
    """Tests for resolving citations to case numbers."""

    def test_resolve_neutral_citation(self):
        """Test resolution of neutral citation to case number."""
        citation = Citation(
            text="2024 NH 123",
            citation_type="neutral",
            year=2024,
            sequence=123,
        )
        
        opinions_index = {
            "2024-0123": "2024-0123",
        }
        
        result = resolve_citation(citation, opinions_index)
        
        assert result is True
        assert citation.resolved_case_number == "2024-0123"
        assert citation.confidence == "high"

    def test_resolve_reporter_citation(self):
        """Test resolution of reporter citation to case number."""
        citation = Citation(
            text="170 N.H. 186",
            citation_type="reporter",
            volume="170",
            page="186",
        )
        
        opinions_index = {
            "170 N.H. 186": "2017-0456",
        }
        
        result = resolve_citation(citation, opinions_index)
        
        assert result is True
        assert citation.resolved_case_number == "2017-0456"

    def test_unresolved_citation_marked_correctly(self):
        """Test that unresolved citations are marked with correct confidence."""
        citation = Citation(
            text="999 N.H. 999",
            citation_type="reporter",
            volume="999",
            page="999",
        )
        
        opinions_index = {}
        
        result = resolve_citation(citation, opinions_index)
        
        assert result is False
        assert citation.confidence == "unresolved"

    def test_resolve_with_year_disambiguation(self):
        """Test resolution using year for disambiguation."""
        citation = Citation(
            text="170 N.H. 186",
            citation_type="reporter",
            volume="170",
            page="186",
            year=2017,
        )
        
        opinions_index = {
            "2017:170 N.H. 186": "2017-0456",
        }
        
        result = resolve_citation(citation, opinions_index)
        
        assert result is True


class TestCitationIndex:
    """Tests for building citation lookup index."""

    def test_build_citation_index(self, sample_opinions_df):
        """Test building citation index from opinions DataFrame."""
        index = build_citation_index(sample_opinions_df)
        
        assert len(index) > 0
        assert "2024-0123" in index
        assert "175 N.H. 456" in index

    def test_index_includes_case_numbers(self, sample_opinions_df):
        """Test that index includes case numbers as keys."""
        index = build_citation_index(sample_opinions_df)
        
        # Case numbers should map to themselves
        assert index.get("2024-0123") == "2024-0123"

    def test_index_includes_year_disambiguation(self, sample_opinions_df):
        """Test that index includes year-prefixed keys for disambiguation."""
        index = build_citation_index(sample_opinions_df)
        
        # Should have year:citation entries
        year_keys = [k for k in index.keys() if ":" in k and k.startswith("202")]
        assert len(year_keys) > 0


class TestCitationDeduplication:
    """Tests for deduplicating citations."""

    def test_deduplicate_removes_duplicate_cases(self):
        """Test that deduplicate removes multiple citations to same case."""
        citation1 = Citation("170 N.H. 186", "reporter")
        citation1.resolved_case_number = "2017-0456"
        citation1.confidence = "high"
        
        citation2 = Citation("2017 NH 456", "neutral")
        citation2.resolved_case_number = "2017-0456"
        citation2.confidence = "high"
        
        result = deduplicate_citations([citation1, citation2])
        
        assert len(result) == 1

    def test_deduplicate_keeps_highest_confidence(self):
        """Test that deduplicate keeps citation with highest confidence."""
        citation1 = Citation("170 N.H. 186", "reporter")
        citation1.resolved_case_number = "2017-0456"
        citation1.confidence = "medium"
        
        citation2 = Citation("2017 NH 456", "neutral")
        citation2.resolved_case_number = "2017-0456"
        citation2.confidence = "high"
        
        result = deduplicate_citations([citation1, citation2])
        
        assert len(result) == 1
        assert result[0].confidence == "high"

    def test_deduplicate_preserves_different_cases(self):
        """Test that deduplicate preserves citations to different cases."""
        citation1 = Citation("170 N.H. 186", "reporter")
        citation1.resolved_case_number = "2017-0456"
        
        citation2 = Citation("171 N.H. 100", "reporter")
        citation2.resolved_case_number = "2018-0123"
        
        result = deduplicate_citations([citation1, citation2])
        
        assert len(result) == 2


class TestCitationDataClass:
    """Tests for Citation data class."""

    def test_citation_to_dict(self):
        """Test converting citation to dictionary."""
        citation = Citation(
            text="170 N.H. 186",
            citation_type="reporter",
            volume="170",
            page="186",
            year=2017,
        )
        
        data = citation.to_dict()
        
        assert data["text"] == "170 N.H. 186"
        assert data["type"] == "reporter"
        assert data["volume"] == "170"
        assert data["year"] == 2017

    def test_citation_repr(self):
        """Test citation string representation."""
        citation = Citation("170 N.H. 186", "reporter")
        
        repr_str = repr(citation)
        
        assert "Citation" in repr_str
        assert "170 N.H. 186" in repr_str
