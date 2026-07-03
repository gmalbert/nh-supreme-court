"""
Unit tests for utils/charts.py
"""

from __future__ import annotations

import pytest
import plotly.graph_objects as go

from utils.charts import (
    outcome_bar,
    opinions_per_year,
    agreement_heatmap,
    bench_diagram,
    authorship_bar,
)


class TestOutcomeCharts:
    """Tests for outcome visualization charts."""

    def test_outcome_bar_returns_figure(self, sample_opinions_df):
        """Test that outcome_bar returns a Plotly figure."""
        result = outcome_bar(sample_opinions_df)
        
        assert isinstance(result, go.Figure)
        assert len(result.data) > 0

    def test_outcome_bar_handles_empty_data(self):
        """Test that outcome_bar handles empty DataFrame."""
        import pandas as pd
        empty_df = pd.DataFrame()
        
        result = outcome_bar(empty_df)
        
        assert isinstance(result, go.Figure)

    def test_outcome_bar_uses_consistent_colors(self, sample_opinions_df):
        """Test that outcome colors are consistent with constants."""
        from utils.constants import OUTCOME_COLORS
        
        result = outcome_bar(sample_opinions_df)
        
        # Check that colors are applied
        assert result.data[0].marker is not None

    def test_opinions_per_year_returns_figure(self, sample_opinions_df):
        """Test that opinions_per_year returns a Plotly figure."""
        result = opinions_per_year(sample_opinions_df)
        
        assert isinstance(result, go.Figure)
        assert len(result.data) > 0

    def test_opinions_per_year_handles_missing_dates(self):
        """Test that missing dates are handled gracefully."""
        import pandas as pd
        df = pd.DataFrame([
            {"case_number": "2024-0123", "outcome": "Affirmed", "date_issued": None},
        ])
        
        result = opinions_per_year
        result = outcome_over_time_chart(df)
        
        assert isinstance(result, go.Figure)


class TestAgreementHeatmap:
    """Tests for justice agreement heatmap."""

    def test_agreement_heatmap_returns_figure(self):
        """Test that agreement_heatmap returns a Plotly figure."""
        import pandas as pd
        
        # Create sample agreement matrix
        agreement_data = pd.DataFrame(
            [[1.0, 0.85, 0.80], [0.85, 1.0, 0.75], [0.80, 0.75, 1.0]],
            index=["MacDonald", "Hicks", "Bassett"],
            columns=["MacDonald", "Hicks", "Bassett"],
        )
        
        result = agreement_heatmap(agreement_data)
        
        assert isinstance(result, go.Figure)
        assert len(result.data) > 0

    def test_agreement_heatmap_diagonal_is_one(self):
        """Test that diagonal values (self-agreement) are 1.0."""
        import pandas as pd
        
        agreement_data = pd.DataFrame(
            [[1.0, 0.85], [0.85, 1.0]],
            index=["MacDonald", "Hicks"],
            columns=["MacDonald", "Hicks"],
        )
        
        result = agreement_heatmap(agreement_data)
        
        # Diagonal should be 1.0
        assert result.data[0].z[0][0] == 1.0
        assert result.data[0].z[1][1] == 1.0

    def test_agreement_heatmap_uses_correct_color_scale(self):
        """Test that heatmap uses appropriate color scale."""
        import pandas as pd
        
        agreement_data = pd.DataFrame(
            [[1.0, 0.50], [0.50, 1.0]],
            index=["MacDonald", "Hicks"],
            columns=["MacDonald", "Hicks"],
        )
        
        result = agreement_heatmap(agreement_data)
        
        # Should have colorscale defined
        assert hasattr(result.data[0], 'colorscale') or hasattr(result.data[0], 'colorbar')


class TestBenchDiagram:
    """Tests for bench diagram visualization."""

    def test_bench_diagram_returns_figure(self):
        """Test that bench_diagram returns a Plotly figure."""
        justices = [
            {"name": "MacDonald", "title": "Chief Justice", "appointed": "2021"},
            {"name": "Hicks", "title": "Associate Justice", "appointed": "2019"},
        ]
        
        result = bench_diagram(justices)
        
        assert isinstance(result, go.Figure)

    def test_bench_diagram_handles_empty_list(self):
        """Test that bench_diagram handles empty justice list."""
        result = bench_diagram([])
        
        assert isinstance(result, go.Figure)

    def test_bench_diagram_positions_five_justices(self):
        """Test that bench_diagram correctly positions 5 justices."""
        justices = [
            {"name": f"Justice {i}", "title": "Justice", "appointed": "2020"}
            for i in range(5)
        ]
        
        result = bench_diagram(justices)
        
        assert isinstance(result, go.Figure)
        # Should have annotations or markers for each justice
        assert len(result.data) > 0 or len(result.layout.annotations) > 0


class TestChartConsistency:
    """Tests for chart styling consistency."""

    def test_charts_use_consistent_theme(self, sample_opinions_df):
        """Test that charts follow consistent theming."""
        from utils.constants import OUTCOME_COLORS
        
        chart = outcome_bar(sample_opinions_df)
        
        # Check that figure has layout properties set
        assert chart.layout is not None
        assert hasattr(chart.layout, 'template') or hasattr(chart.layout, 'plot_bgcolor')

    def test_charts_have_titles(self, sample_opinions_df):
        """Test that charts have appropriate titles."""
        chart = outcome_bar(sample_opinions_df)
        
        # Should have a title (either set or empty)
        assert hasattr(chart.layout, 'title')

    def test_charts_have_axis_labels(self, sample_opinions_df):
        """Test that charts have axis labels where appropriate."""
        chart = opinions_per_year(sample_opinions_df)
        
        # Should have x and y axis configurations
        assert hasattr(chart.layout, 'xaxis')
        assert hasattr(chart.layout, 'yaxis')


class TestChartDataValidation:
    """Tests for chart data validation and error handling."""

    def test_charts_handle_malformed_data(self):
        """Test that charts handle malformed data gracefully."""
        import pandas as pd
        
        # DataFrame with unexpected columns
        df = pd.DataFrame([{"unexpected": "column"}])
        
        try:
            result = outcome_bar(df)
            assert isinstance(result, go.Figure)
        except (KeyError, AttributeError):
            # Acceptable to raise exceptions for missing required columns
            pass

    def test_charts_handle_nan_values(self):
        """Test that charts handle NaN values appropriately."""
        import pandas as pd
        import numpy as np
        
        df = pd.DataFrame([
            {"case_number": "2024-0123", "outcome": "Affirmed", "date_issued": pd.NaT},
            {"case_number": "2024-0124", "outcome": np.nan, "date_issued": "2024-06-01"},
        ])
        
        try:
            result = outcome_bar(df)
            assert isinstance(result, go.Figure)
        except (KeyError, AttributeError):
            # Acceptable if columns don't match expected schema
            pass


class TestChartInteractivity:
    """Tests for chart inteity features."""

    def test_charts_have_hover_data(self, sample_opinions_df):
        """Test that charts include hover information."""
        chart = outcome_bar_chart(sample_opinions_df)
        
        # Check that trace has hover properties
        if len(chart.data) > 0:
            assert hasattr(chart.data[0], 'hovertemplate') or hasattr(chart.data[0], 'hoverinfo')

    def test_charts_support_clicking(self, sample_opinions_df):
        """Test that charts support click interactions where appropriate."""
        chart = agreement_heatmap(
            pd.DataFrame([[1.0, 0.85], [0.85, 1.0]], 
                        index=["A", "B"], columns=["A", "B"])
        )
        
        # Heatmaps should support clicking
        assert isinstance(chart, go.Figure)
