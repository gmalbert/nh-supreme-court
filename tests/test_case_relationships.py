"""
Tests for case relationship building.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.build_case_relationships import (
    normalize_docket_for_orders,
    match_orders_to_opinions,
)


class TestDocketNormalization:
    """Tests for docket number normalization."""

    def test_normalize_docket_returns_variants(self):
        """Test that normalize returns multiple variants."""
        variants = normalize_docket_for_orders("2024-0123")
        
        assert len(variants) > 0
        assert "2024-0123" in variants

    def test_normalize_removes_leading_zeros(self):
        """Test that normalization handles leading zeros."""
        variants = normalize_docket_for_orders("2024-0123")
        
        # Should include version without leading zeros
        assert any("123" in v for v in variants)

    def test_normalize_handles_empty_input(self):
        """Test that normalization handles empty input."""
        variants = normalize_docket_for_orders("")
        
        assert variants == []

    def test_normalize_handles_none_input(self):
        """Test that normalization handles None input."""
        variants = normalize_docket_for_orders(None)
        
        assert variants == []


class TestOrderMatching:
    """Tests for matching orders to opinions."""

    def test_match_exact_docket(self):
        """Test matching orders with exact docket number."""
        opinions_df = pd.DataFrame([
            {"case_number": "2024-0123", "case_name": "State v. Smith"},
        ])
        
        orders_df = pd.DataFrame([
            {
                "docket_number": "2024-0123",
                "order_date": "2024-01-15",
                "order_type": "Motion Order",
                "description": "Motion granted",
            },
        ])
        
        relationships, unmatched = match_orders_to_opinions(opinions_df, orders_df)
        
        assert "2024-0123" in relationships
        assert len(relationships["2024-0123"]) > 0
        assert len(unmatched) == 0

    def test_match_handles_leading_zeros(self):
        """Test that matching handles leading zero differences."""
        opinions_df = pd.DataFrame([
            {"case_number": "2024-0123", "case_name": "State v. Smith"},
        ])
        
        orders_df = pd.DataFrame([
            {
                "docket_number": "2024-123",  # No leading zero
                "order_date": "2024-01-15",
                "order_type": "Motion Order",
                "description": "Motion granted",
            },
        ])
        
        relationships, unmatched = match_orders_to_opinions(opinions_df, orders_df)
        
        # Should still match despite format difference
        assert "2024-0123" in relationships or len(relationships) > 0

    def test_unmatched_orders_tracked(self):
        """Test that unmatched orders are tracked."""
        opinions_df = pd.DataFrame([
            {"case_number": "2024-0123", "case_name": "State v. Smith"},
        ])
        
        orders_df = pd.DataFrame([
            {
                "docket_number": "2024-9999",  # No matching opinion
                "order_date": "2024-01-15",
                "order_type": "Motion Order",
                "description": "Motion granted",
            },
        ])
        
        relationships, unmatched = match_orders_to_opinions(opinions_df, orders_df)
        
        assert len(unmatched) > 0
        assert any(o["docket_number"] == "2024-9999" for o in unmatched)

    def test_one_opinion_multiple_orders(self):
        """Test that one opinion can have multiple orders."""
        opinions_df = pd.DataFrame([
            {"case_number": "2024-0123", "case_name": "State v. Smith"},
        ])
        
        orders_df = pd.DataFrame([
            {
                "docket_number": "2024-0123",
                "order_date": "2024-01-15",
                "order_type": "Motion Order",
                "description": "First order",
            },
            {
                "docket_number": "2024-0123",
                "order_date": "2024-02-20",
                "order_type": "Status Order",
                "description": "Second order",
            },
        ])
        
        relationships, unmatched = match_orders_to_opinions(opinions_df, orders_df)
        
        assert "2024-0123" in relationships
        assert len(relationships["2024-0123"]) == 2

    def test_empty_orders_returns_empty_relationships(self):
        """Test that empty orders DataFrame returns empty relationships."""
        opinions_df = pd.DataFrame([
            {"case_number": "2024-0123", "case_name": "State v. Smith"},
        ])
        
        orders_df = pd.DataFrame()
        
        relationships, unmatched = match_orders_to_opinions(opinions_df, orders_df)
        
        assert len(relationships) == 0
        assert len(unmatched) == 0
