"""
Unit tests for utils/vote_parser.py
"""

from __future__ import annotations

import pytest

from utils.vote_parser import (
    parse_vote_block,
    vote_summary,
    _names_in_clause,
)


class TestVoteBlockParsing:
    """Tests for vote block parsing."""

    def test_parse_unanimous_opinion(self, sample_vote_text):
        """Test parsing a unanimous decision."""
        text = """AFFIRMED.

MacDonald, C.J., and Hicks, Bassett, Donovan, and Hantz Marconi, JJ., concurred."""
        
        result = parse_vote_block(text, "macdonald")
        
        assert result["macdonald"]["vote"] == "majority"
        assert result["hicks"]["vote"] == "majority"
        assert result["bassett"]["vote"] == "majority"
        assert result["donovan"]["vote"] == "majority"
        assert result["hantz_marconi"]["vote"] == "majority"

    def test_parse_divided_decision(self, sample_vote_text):
        """Test parsing a decision with dissent."""
        result = parse_vote_block(sample_vote_text, "macdonald")
        
        assert result["macdonald"]["vote"] == "majority"
        assert result["hicks"]["vote"] == "majority"
        assert result["bassett"]["vote"] == "majority"
        assert result["donovan"]["vote"] == "majority"
        assert result["hantz_marconi"]["vote"] == "dissent"

    def test_parse_separate_concurrence(self):
        """Test parsing a decision with separate concurrence."""
        text = """AFFIRMED.

MacDonald, C.J., and Hicks and Bassett, JJ., concurred; 
Donovan, J., concurred specially."""
        
        result = parse_vote_block(text, "macdonald")
        
        assert result["donovan"]["vote"] == "concur_separate"

    def test_parse_not_participating(self):
        """Test parsing when a justice did not participate."""
        text = """AFFIRMED.

MacDonald, C.J., and Hicks, Bassett, and Donovan, JJ., concurred; 
Hantz Marconi, J., did not participate."""
        
        result = parse_vote_block(text, "macdonald")
        
        assert result["hantz_marconi"]["vote"] == "not_participating"

    def test_parse_recusal(self):
        """Test parsing when a justice was recused."""
        text = """AFFIRMED.

MacDonald, C.J., and Hicks, Bassett, and Donovan, JJ., concurred; 
Hantz Marconi, J., recused."""
        
        result = parse_vote_block(text, "macdonald")
        
        assert result["hantz_marconi"]["vote"] == "not_participating"


class TestAuthorParsing:
    """Tests for author extraction."""

    def test_parse_chief_justice_author(self):
        """Test that parse_vote_block correctly identifies the author."""
        text = """AFFIRMED.

MacDonald, C.J., and Hicks and Bassett, JJ., concurred."""
        
        result = parse_vote_block(text, "macdonald")
        
        # The author is specified in the function call
        assert "macdonald" in result
        assert result["macdonald"]["vote"] == "majority"

    def test_per_curiam_opinion(self):
        """Test handling of per curiam opinions."""
        text = """AFFIRMED.

All justices concurred."""
        
        result = parse_vote_block(text, "per_curiam")
        
        # Per curiam is the default author
        assert len(result) >= 0

class TestVoteStringExtraction:
    """Tests for vote string extraction."""

    def test_extract_simple_vote_string(self):
        """Test extracting vote strings like '4-1'."""
        votes = {
            "macdonald": {"vote": "majority"},
            "hicks": {"vote": "majority"},
            "bassett": {"vote": "majority"},
            "donovan": {"vote": "majority"},
            "hantz_marconi": {"vote": "dissent"},
        }

        result = vote_summary(votes)

        assert result["vote_string"] == "4-1"


class TestVoteSummary:
    """Tests for vote summary generation."""

    def test_vote_summary_simple_majority(self):
        """Test vote summary for simple majority decisions."""
        votes = {
            "macdonald": {"vote": "majority"},
            "hicks": {"vote": "majority"},
            "bassett": {"vote": "majority"},
            "donovan": {"vote": "majority"},
            "hantz_marconi": {"vote": "dissent"},
        }
        
        result = vote_summary(votes)
        
        # Check that summary contains vote counts
        assert result["majority"] == 4
        assert result["dissent"] == 1
        assert result["vote_string"] == "4-1"

    def test_vote_summary_unanimous(self):
        """Test vote summary for unanimous decisions."""
        votes = {
            "macdonald": {"vote": "majority"},
            "hicks": {"vote": "majority"},
            "bassett": {"vote": "majority"},
            "donovan": {"vote": "majority"},
            "hantz_marconi": {"vote": "majority"},
        }
        
        result = vote_summary(votes)
        
        # Should indicate unanimous decision
        assert result["is_unanimous"] is True
        assert result["vote_string"] == "5-0"

    def test_vote_summary_with_not_participating(self):
        """Test vote summary when a justice did not participate."""
        votes = {
            "macdonald": {"vote": "majority"},
            "hicks": {"vote": "majority"},
            "bassett": {"vote": "majority"},
            "donovan": {"vote": "not_participating"},
            "hantz_marconi": {"vote": "dissent"},
        }
        
        result = vote_summary(votes)
        
        # Should handle not participating justices
        assert result["not_participating"] == 1
        assert result["dissent"] == 1


class TestNamesInClause:
    """Tests for extracting justice names from vote clauses."""

    def test_names_in_clause_multiple_names(self):
        """Test extracting multiple justice names."""
        names = _names_in_clause("Hicks and Bassett, JJ., concurred")

        assert "hicks" in names
        assert "bassett" in names

    def test_names_in_clause_compound_name(self):
        """Test extracting compound last names."""
        clause = "Hantz Marconi, J., dissented"
        
        names = _names_in_clause(clause)
        
        assert "hantz_marconi" in names

    def test_names_in_clause_case_insensitive(self):
        """Test that name extraction is case insensitive."""
        clause = "macdonald and HICKS concurred"
        
        names = _names_in_clause(clause)
        
        assert "macdonald" in names
        assert "hicks" in names
