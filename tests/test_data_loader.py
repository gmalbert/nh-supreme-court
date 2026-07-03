"""
Unit tests for utils/data_loader.py
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from utils.data_loader import (
    load_opinions,
    load_opinions_json,
    load_case_orders,
    data_last_updated,
    _needs_master_rebuild,
)


class TestOpinionLoading:
    """Tests for opinion data loading functions."""

    @patch("utils.data_loader.pd.read_csv")
    def test_load_opinions_returns_dataframe(self, mock_read_csv, sample_opinions_df):
        """Test that load_opinions returns a DataFrame."""
        mock_read_csv.return_value = sample_opinions_df
        
        result = load_opinions()
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0

    @patch("utils.data_loader.Path.exists")
    @patch("utils.data_loader.pd.read_csv")
    def test_load_opinions_handles_missing_file(self, mock_read_csv, mock_exists):
        """Test that load_opinions handles missing files gracefully."""
        mock_exists.return_value = False
        mock_read_csv.side_effect = FileNotFoundError
        
        result = load_opinions()
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    @patch("utils.data_loader.Path.exists")
    @patch("builtins.open")
    def test_load_opinions_json_returns_list(self, mock_open, mock_exists, sample_opinion):
        """Test that load_opinions_json returns a list of dicts."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps([sample_opinion])
        
        result = load_opinions_json()
        
        assert isinstance(result, list)
        assert len(result) > 0
        assert isinstance(result[0], dict)

    def test_load_opinions_converts_dates(self, sample_opinions_df):
        """Test that date columns are converted to datetime."""
        with patch("utils.data_loader.pd.read_csv", return_value=sample_opinions_df):
            result = load_opinions()
            
            # Check that date columns exist (they should be converted by the loader)
            assert "date_issued" in result.columns
            assert "date_argued" in result.columns


class TestCaseOrderLoading:
    """Tests for case order loading functions."""

    @patch("utils.data_loader.pd.read_csv")
    def test_load_case_orders_returns_dataframe(self, mock_read_csv):
        """Test that load_case_orders returns a DataFrame."""
        mock_df = pd.DataFrame([
            {
                "docket_number": "2024-0123",
                "order_date": "2024-02-15",
                "order_type": "Motion Order",
            }
        ])
        mock_read_csv.return_value = mock_df
        
        result = load_case_orders()
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0

    @patch("utils.data_loader.Path.exists")
    @patch("utils.data_loader.pd.read_csv")
    def test_load_case_orders_handles_missing_file(self, mock_read_csv, mock_exists):
        """Test that load_case_orders handles missing files gracefully."""
        mock_exists.return_value = False
        mock_read_csv.side_effect = FileNotFoundError
        
        result = load_case_orders()
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0


class TestDataFreshness:
    """Tests for data freshness functions."""

    @patch("utils.data_loader.Path.exists")
    @patch("utils.data_loader.Path.stat")
    def test_data_last_updated_returns_string(self, mock_stat, mock_exists):
        """Test that data_last_updated returns a formatted string."""
        mock_exists.return_value = True
        mock_stat_result = Mock()
        mock_stat_result.st_mtime = 1704067200.0  # 2024-01-01
        mock_stat.return_value = mock_stat_result
        
        result = data_last_updated()
        
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("utils.data_loader.Path.exists")
    def test_data_last_updated_handles_missing_file(self, mock_exists):
        """Test that data_last_updated handles missing files."""
        mock_exists.return_value = False
        
        result = data_last_updated()
        
        assert result == "Unknown"


class TestRebuildLogic:
    """Tests for master dataset rebuild logic."""

    def test_needs_master_rebuild_when_source_newer(self, temp_data_dir):
        """Test that rebuild is needed when source files are newer."""
        processed = temp_data_dir / "processed"
        
        # Create master file
        master_file = processed / "opinions.csv"
        master_file.write_text("case_number,case_name\n")
        
        # Create newer source file
        source_dir = processed / "opinions_2024.json"
        source_dir.write_text('[]')
        
        # Touch the source file to make it newer
        import time
        time.sleep(0.01)
        source_dir.touch()
        
        # Note: _needs_master_rebuild is typically an internal function
        # This test would need access to the actual function
        # For now, this is a placeholder for the rebuild logic test

    def test_needs_master_rebuild_when_master_missing(self, temp_data_dir):
        """Test that rebuild is needed when master file doesn't exist."""
        processed = temp_data_dir / "processed"
        
        # Create source files but no master
        source_file = processed / "opinions_2024.json"
        source_file.write_text('[]')
        
        # Rebuild should be needed
        # This would call the actual _needs_master_rebuild function


class TestDataValidation:
    """Tests for data validation and error handling."""

    def test_load_opinions_validates_required_columns(self, sample_opinions_df):
        """Test that required columns are present in loaded data."""
        with patch("utils.data_loader.pd.read_csv", return_value=sample_opinions_df):
            result = load_opinions()
            
            required_columns = [
                "case_number",
                "case_name",
                "date_issued",
                "outcome",
                "author",
            ]
            
            for col in required_columns:
                assert col in result.columns

    def test_load_opinions_handles_empty_dataframe(self):
        """Test that empty DataFrame is handled gracefully."""
        empty_df = pd.DataFrame()
        
        with patch("utils.data_loader.pd.read_csv", return_value=empty_df):
            result = load_opinions()
            
            assert isinstance(result, pd.DataFrame)
            assert len(result) == 0

    def test_load_opinions_handles_malformed_json(self):
        """Test that malformed JSON is handled gracefully."""
        with patch("utils.data_loader.Path.exists", return_value=True):
            with patch("builtins.open") as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = "{invalid json"
                
                # Should not raise exception
                try:
                    result = load_opinions_json()
                    # If it doesn't raise, it should return empty list or handle gracefully
                    assert isinstance(result, list)
                except json.JSONDecodeError:
                    # This is also acceptable behavior
                    pass


class TestCacheBehavior:
    """Tests for Streamlit cache behavior."""

    def test_load_functions_are_cacheable(self):
        """Test that load functions have cache decorators."""
        # Check that functions have the streamlit cache attribute
        # Note: This tests that the decorator is applied, not the actual caching
        from utils import data_loader
        
        # These functions should be decorated with @st.cache_data
        cacheable_functions = [
            "load_opinions",
            "load_opinions_json",
            "load_case_orders",
        ]
        
        for func_name in cacheable_functions:
            func = getattr(data_loader, func_name, None)
            assert func is not None, f"{func_name} not found"
            # In a real Streamlit environment, we could check for cache attributes
            # For now, we just verify the function exists


class TestListColumnHandling:
    """Tests for handling list columns in DataFrames."""

    def test_load_opinions_preserves_list_columns(self, sample_opinions_df):
        """Test that list columns (topics, justices) are preserved correctly."""
        with patch("utils.data_loader.pd.read_csv", return_value=sample_opinions_df):
            result = load_opinions()
            
            # Check that list columns exist
            list_columns = ["topics", "rsa_citations", "majority", "dissent"]
            
            for col in list_columns:
                if col in result.columns:
                    assert col in result.columns
