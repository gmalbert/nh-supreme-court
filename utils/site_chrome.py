"""
Shared UI components for site chrome (headers, footers, data status, etc.)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent


def render_data_status(manifest_path: Optional[Path] = None) -> None:
    """
    Render data freshness status in sidebar.
    
    Args:
        manifest_path: Path to refresh_manifest.json (defaults to standard location)
    """
    if manifest_path is None:
        manifest_path = ROOT / "data" / "processed" / "refresh_manifest.json"
    
    # Load manifest if available
    manifest = {}
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except Exception:
            pass
    
    # Display status
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 📊 Data Status")
        
        if manifest:
            # Refresh timestamp
            refresh_ts = manifest.get("refresh_timestamp", "")
            if refresh_ts:
                try:
                    dt = datetime.fromisoformat(refresh_ts.replace("Z", "+00:00"))
                    st.caption(f"**Last updated:** {dt.strftime('%B %d, %Y')}")
                except Exception:
                    st.caption(f"**Last updated:** {refresh_ts}")
            
            # Workflow status
            steps = manifest.get("steps", {})
            if steps:
                all_success = all(status == "success" for status in steps.values())
                
                if all_success:
                    st.success("✓ All refresh steps successful", icon="✅")
                else:
                    failed_steps = [step for step, status in steps.items() if status != "success"]
                    st.warning(f"⚠️ {len(failed_steps)} step(s) had issues", icon="⚠️")
        else:
            # No manifest - use fallback
            opinions_csv = ROOT / "data" / "processed" / "opinions.csv"
            if opinions_csv.exists():
                mtime = datetime.fromtimestamp(opinions_csv.stat().st_mtime)
                st.caption(f"**Data from:** {mtime.strftime('%B %d, %Y')}")
            else:
                st.caption("**Status:** No data available")
        
        # Link to court website
        st.caption("[NH Supreme Court →](https://www.courts.nh.gov/supreme-court)")


def render_error_report_link(
    case_number: Optional[str] = None,
    page: Optional[str] = None,
    issue_type: str = "parsing-error",
) -> None:
    """
    Render a "Report Error" link that pre-fills a GitHub issue.
    
    Args:
        case_number: Case number to include in report
        page: Page name where error occurred
        issue_type: Type of issue (parsing-error, data-issue, ui-bug)
    """
    # Build GitHub issue URL
    repo_url = "https://github.com/gmalbert/nh-supreme-court"
    
    title = f"Data Issue: {case_number}" if case_number else "Data Issue"
    
    body_parts = ["## Issue Description", "", "<!-- Describe the issue you encountered -->", ""]
    
    if case_number:
        body_parts.extend([
            "## Case Information",
            f"- **Case Number:** {case_number}",
            "",
        ])
    
    if page:
        body_parts.extend([
            "## Location",
            f"- **Page:** {page}",
            "",
        ])
    
    body_parts.extend([
        "## Expected Behavior",
        "",
        "<!-- What did you expect to see? -->",
        "",
        "## Actual Behavior",
        "",
        "<!-- What actually happened? -->",
        "",
    ])
    
    body = "\n".join(body_parts)
    
    # URL encode
    import urllib.parse
    issue_url = f"{repo_url}/issues/new?title={urllib.parse.quote(title)}&body={urllib.parse.quote(body)}&labels={issue_type}"
    
    st.markdown(f"[🐛 Report an error]({issue_url})")


def render_recent_decisions(opinions_df, limit: int = 10) -> None:
    """
    Render a list of recent decisions.
    
    Args:
        opinions_df: DataFrame with opinion data
        limit: Number of recent decisions to show
    """
    import pandas as pd
    
    if opinions_df.empty:
        st.info("No recent decisions available")
        return
    
    # Sort by date and get most recent
    df = opinions_df.copy()
    
    # Ensure date_issued is datetime
    if "date_issued" in df.columns:
        df["date_issued"] = pd.to_datetime(df["date_issued"], errors="coerce")
        df = df.dropna(subset=["date_issued"])
        df = df.sort_values("date_issued", ascending=False)
        recent = df.head(limit)
        
        st.markdown("### 📰 Recent Decisions")
        
        for _, row in recent.iterrows():
            date_str = row["date_issued"].strftime("%b %d, %Y")
            case_name = row.get("case_name", "Unknown")
            case_number = row.get("case_number", "")
            outcome = row.get("outcome", "")
            
            # Create clickable link (assumes query param routing)
            link = f"?case={case_number}"
            
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**[{case_name}]({link})**")
                st.caption(f"{case_number} • {date_str}")
            with col2:
                if outcome:
                    # Color code outcomes
                    outcome_colors = {
                        "Affirmed": "🟢",
                        "Reversed": "🔴",
                        "Remanded": "🟡",
                        "Vacated": "🟠",
                    }
                    icon = outcome_colors.get(outcome, "⚪")
                    st.caption(f"{icon} {outcome}")
    else:
        st.info("Date information not available")


def get_responsive_css() -> str:
    """
    Get responsive CSS for mobile/tablet/desktop layouts.
    
    Returns:
        CSS string to inject with st.markdown
    """
    css = """
    <style>
    /* Mobile styles (< 768px) */
    @media (max-width: 767px) {
        /* Make columns stack */
        .stColumns > div {
            width: 100% !important;
            min-width: 100% !important;
        }
        
        /* Increase tap target size */
        button, a, .stButton > button {
            min-height: 44px !important;
            min-width: 44px !important;
        }
        
        /* Make tables scrollable */
        .stDataFrame {
            overflow-x: auto !important;
            max-width: 100vw !important;
        }
        
        /* Adjust padding */
        .main .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        
        /* Make filters accordion-style on mobile */
        .stSidebar {
            width: 100% !important;
        }
    }
    
    /* Tablet styles (768px - 1024px) */
    @media (min-width: 768px) and (max-width: 1024px) {
        .main .block-container {
            max-width: 100% !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
        
        /* Adjust column widths for tablet */
        .stColumns > div {
            flex: 1 1 0 !important;
        }
    }
    
    /* Desktop styles (> 1024px) */
    @media (min-width: 1025px) {
        .main .block-container {
            max-width: 1400px !important;
        }
    }
    
    /* Accessibility improvements */
    a:focus, button:focus, input:focus, select:focus {
        outline: 2px solid #4A90E2 !important;
        outline-offset: 2px !important;
    }
    
    /* High contrast links */
    a {
        text-decoration: underline !important;
    }
    
    /* Skip to main content link (hidden until focused) */
    .skip-to-main {
        position: absolute;
        top: -40px;
        left: 0;
        background: #000;
        color: #fff;
        padding: 8px;
        z-index: 100;
    }
    
    .skip-to-main:focus {
        top: 0;
    }
    </style>
    """
    return css


def render_responsive_css() -> None:
    """Inject responsive CSS into the page."""
    st.markdown(get_responsive_css(), unsafe_allow_html=True)
