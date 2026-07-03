"""
Bookmarks and favorites manager using Streamlit session state.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def initialize_bookmarks() -> None:
    """Initialize bookmarks in session state if not already present."""
    if "bookmarks" not in st.session_state:
        st.session_state.bookmarks = []


def add_bookmark(case_number: str, case_name: str, citation: str = "") -> None:
    """
    Add a case to bookmarks.
    
    Args:
        case_number: Case number
        case_name: Case name
        citation: Optional citation
    """
    initialize_bookmarks()
    
    # Check if already bookmarked
    if any(b["case_number"] == case_number for b in st.session_state.bookmarks):
        return
    
    bookmark = {
        "case_number": case_number,
        "case_name": case_name,
        "citation": citation,
    }
    
    st.session_state.bookmarks.append(bookmark)


def remove_bookmark(case_number: str) -> None:
    """Remove a case from bookmarks."""
    initialize_bookmarks()
    
    st.session_state.bookmarks = [
        b for b in st.session_state.bookmarks
        if b["case_number"] != case_number
    ]


def is_bookmarked(case_number: str) -> bool:
    """Check if a case is bookmarked."""
    initialize_bookmarks()
    
    return any(b["case_number"] == case_number for b in st.session_state.bookmarks)


def get_bookmarks() -> list[dict[str, Any]]:
    """Get all bookmarked cases."""
    initialize_bookmarks()
    
    return st.session_state.bookmarks.copy()


def clear_bookmarks() -> None:
    """Clear all bookmarks."""
    st.session_state.bookmarks = []


def render_bookmark_button(case_number: str, case_name: str, citation: str = "") -> None:
    """
    Render a bookmark toggle button.
    
    Args:
        case_number: Case number
        case_name: Case name
        citation: Optional citation
    """
    initialize_bookmarks()
    
    bookmarked = is_bookmarked(case_number)
    
    if bookmarked:
        if st.button("🔖 Bookmarked", key=f"bookmark_{case_number}", help="Remove from bookmarks"):
            remove_bookmark(case_number)
            st.rerun()
    else:
        if st.button("📑 Bookmark", key=f"bookmark_{case_number}", help="Add to bookmarks"):
            add_bookmark(case_number, case_name, citation)
            st.rerun()


def render_bookmarks_sidebar() -> None:
    """Render bookmarks section in sidebar."""
    initialize_bookmarks()
    
    bookmarks = get_bookmarks()
    
    if not bookmarks:
        return
    
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 🔖 Bookmarked Cases")
        
        for bookmark in bookmarks[:5]:  # Show first 5
            case_num = bookmark["case_number"]
            case_name = bookmark["case_name"]
            
            # Truncate long names
            if len(case_name) > 30:
                case_name = case_name[:27] + "..."
            
            col1, col2 = st.columns([4, 1])
            with col1:
                st.caption(f"[{case_name}](?case={case_num})")
            with col2:
                if st.button("×", key=f"remove_{case_num}", help="Remove"):
                    remove_bookmark(case_num)
                    st.rerun()
        
        if len(bookmarks) > 5:
            st.caption(f"+{len(bookmarks) - 5} more")
        
        if st.button("Clear all", key="clear_bookmarks"):
            clear_bookmarks()
            st.rerun()
