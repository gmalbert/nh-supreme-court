"""
Tests for utils/opinion_search.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from utils.opinion_search import (
    create_index,
    index_opinion,
    search,
    get_snippet,
    rebuild_index,
)


class TestSearchIndex:
    """Tests for search index creation and management."""

    def test_create_index_creates_table(self, tmp_path):
        """Test that create_index creates the FTS5 table."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        create_index(conn)
        
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='opinions_fts'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_index_opinion_adds_record(self, tmp_path):
        """Test that index_opinion adds a record to the index."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        create_index(conn)
        
        index_opinion(
            conn,
            case_number="2024-0123",
            citation="175 N.H. 456",
            case_name="State v. Smith",
            full_text="This is the full opinion text about reasonable expectation of privacy.",
            summary="Summary of the case",
            topics="Criminal Law, Evidence",
            author="MacDonald",
            outcome="Affirmed",
            year=2024,
        )
        conn.commit()
        
        cursor = conn.execute("SELECT COUNT(*) FROM opinions_fts")
        count = cursor.fetchone()[0]
        assert count == 1
        conn.close()


class TestSearch:
    """Tests for search functionality."""

    @pytest.fixture
    def populated_index(self, tmp_path):
        """Create a populated search index for testing."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        create_index(conn)
        
        # Add test opinions
        index_opinion(
            conn, "2024-0123", "175 N.H. 456", "State v. Smith",
            "Opinion about reasonable expectation of privacy in vehicle searches.",
            "Vehicle search case", "Criminal Law", "MacDonald", "Affirmed", 2024
        )
        index_opinion(
            conn, "2024-0124", "175 N.H. 457", "Doe v. Public Service",
            "Negligence case about utility company liability.",
            "Utility negligence", "Torts", "Hicks", "Reversed", 2024
        )
        conn.commit()
        
        yield conn
        conn.close()

    def test_search_finds_term_in_full_text(self, populated_index):
        """Test that search finds terms in full text."""
        results = search("privacy", conn=populated_index)
        
        assert len(results) > 0
        assert any("Smith" in r["case_name"] for r in results)

    def test_search_phrase_query(self, populated_index):
        """Test phrase search with quotes."""
        results = search('"expectation of privacy"', conn=populated_index)
        
        assert len(results) > 0

    def test_search_with_year_filter(self, populated_index):
        """Test search with year filter."""
        results = search("case", conn=populated_index, year_filter=[2024])
        
        assert len(results) > 0
        assert all(r["year"] == 2024 for r in results)

    def test_search_with_outcome_filter(self, populated_index):
        """Test search with outcome filter."""
        results = search("case", conn=populated_index, outcome_filter=["Affirmed"])
        
        assert len(results) > 0
        assert all(r["outcome"] == "Affirmed" for r in results)

    def test_search_returns_ranked_results(self, populated_index):
        """Test that search returns results with rank scores."""
        results = search("negligence", conn=populated_index)
        
        assert len(results) > 0
        assert all("rank" in r for r in results)


class TestSnippet:
    """Tests for snippet extraction."""

    def test_get_snippet_extracts_context(self):
        """Test that get_snippet extracts context around query terms."""
        text = "This is a long opinion about reasonable expectation of privacy in vehicle searches under the Fourth Amendment."
        
        snippet = get_snippet(text, ["privacy"])
        
        assert "privacy" in snippet.lower()
        assert len(snippet) < len(text)

    def test_get_snippet_highlights_terms(self):
        """Test that get_snippet highlights query terms."""
        text = "The court held that privacy rights apply."
        
        snippet = get_snippet(text, ["privacy"])
        
        assert "**privacy**" in snippet or "**Privacy**" in snippet

    def test_get_snippet_handles_multiple_terms(self):
        """Test that get_snippet handles multiple query terms."""
        text = "The expectation of privacy in vehicles is different from homes."
        
        snippet = get_snippet(text, ["privacy", "vehicles"])
        
        assert "privacy" in snippet.lower()

    def test_get_snippet_adds_ellipsis(self):
        """Test that get_snippet adds ellipsis for truncated text."""
        text = "A" * 500
        
        snippet = get_snippet(text, ["test"])
        
        assert "..." in snippet


class TestRebuildIndex:
    """Tests for index rebuilding."""

    def test_rebuild_index_processes_opinions(self, tmp_path, sample_opinions_df):
        """Test that rebuild_index processes all opinions."""
        # Create temporary DB path
        import utils.opinion_search as search_module
        original_path = search_module.SEARCH_INDEX_PATH
        search_module.SEARCH_INDEX_PATH = tmp_path / "test.db"
        
        try:
            opinion_texts = {
                "2024-0123": "Full text of opinion about privacy rights.",
                "2024-0124": "Full text of negligence case.",
            }
            
            count = rebuild_index(sample_opinions_df.head(2), opinion_texts)
            
            assert count == 2
        finally:
            search_module.SEARCH_INDEX_PATH = original_path

    def test_rebuild_index_clears_existing_data(self, tmp_path, sample_opinions_df):
        """Test that rebuild_index clears existing data."""
        import utils.opinion_search as search_module
        original_path = search_module.SEARCH_INDEX_PATH
        search_module.SEARCH_INDEX_PATH = tmp_path / "test.db"
        
        try:
            opinion_texts = {"2024-0123": "Text"}
            
            # Build once
            rebuild_index(sample_opinions_df.head(1), opinion_texts)
            
            # Rebuild with different data
            count = rebuild_index(sample_opinions_df.head(1), opinion_texts)
            
            # Should have only 1 record, not 2
            conn = sqlite3.connect(str(search_module.SEARCH_INDEX_PATH))
            cursor = conn.execute("SELECT COUNT(*) FROM opinions_fts")
            actual_count = cursor.fetchone()[0]
            conn.close()
            
            assert actual_count == count
        finally:
            search_module.SEARCH_INDEX_PATH = original_path
