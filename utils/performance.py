"""
Performance optimization utilities for Streamlit app.
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable

import streamlit as st


def profile_function(func: Callable) -> Callable:
    """
    Decorator to profile function execution time.
    
    Usage:
        @profile_function
        def my_slow_function():
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        
        if elapsed > 1.0:  # Log slow functions
            print(f"⏱️  {func.__name__} took {elapsed:.2f}s")
        
        return result
    
    return wrapper


def paginate_dataframe(df, page_size: int = 50, page_key: str = "page"):
    """
    Paginate a large DataFrame for display.
    
    Args:
        df: DataFrame to paginate
        page_size: Rows per page
        page_key: Session state key for page number
    
    Returns:
        Paginated DataFrame slice
    """
    total_pages = (len(df) - 1) // page_size + 1
    
    if f"{page_key}_num" not in st.session_state:
        st.session_state[f"{page_key}_num"] = 1
    
    # Pagination controls
    col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
    
    with col1:
        if st.button("⏮️ First", key=f"{page_key}_first"):
            st.session_state[f"{page_key}_num"] = 1
    
    with col2:
        if st.button("◀️ Prev", key=f"{page_key}_prev"):
            if st.session_state[f"{page_key}_num"] > 1:
                st.session_state[f"{page_key}_num"] -= 1
    
    with col3:
        st.markdown(f"**Page {st.session_state[f'{page_key}_num']} of {total_pages}**")
    
    with col4:
        if st.button("Next ▶️", key=f"{page_key}_next"):
            if st.session_state[f"{page_key}_num"] < total_pages:
                st.session_state[f"{page_key}_num"] += 1
    
    with col5:
        if st.button("Last ⏭️", key=f"{page_key}_last"):
            st.session_state[f"{page_key}_num"] = total_pages
    
    # Get page slice
    start_idx = (st.session_state[f"{page_key}_num"] - 1) * page_size
    end_idx = start_idx + page_size
    
    return df.iloc[start_idx:end_idx]


def lazy_load_data(load_func: Callable, cache_key: str, ttl: int = 3600) -> Any:
    """
    Lazy load data with caching.
    
    Args:
        load_func: Function to load data
        cache_key: Unique cache key
        ttl: Cache time-to-live in seconds
    
    Returns:
        Loaded data
    """
    @st.cache_data(ttl=ttl)
    def _cached_load():
        return load_func()
    
    return _cached_load()


def batch_process_with_progress(
    items: list,
    process_func: Callable,
    batch_size: int = 100,
    progress_label: str = "Processing...",
):
    """
    Process items in batches with progress bar.
    
    Args:
        items: List of items to process
        process_func: Function to process each item
        batch_size: Items per batch
        progress_label: Progress bar label
    
    Returns:
        List of results
    """
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_items = len(items)
    
    for i in range(0, total_items, batch_size):
        batch = items[i:i + batch_size]
        
        # Process batch
        batch_results = [process_func(item) for item in batch]
        results.extend(batch_results)
        
        # Update progress
        progress = min((i + batch_size) / total_items, 1.0)
        progress_bar.progress(progress)
        status_text.text(f"{progress_label} {i + len(batch)}/{total_items}")
    
    progress_bar.empty()
    status_text.empty()
    
    return results


def optimize_dataframe_dtypes(df):
    """
    Optimize DataFrame memory usage by downcasting dtypes.
    
    Args:
        df: DataFrame to optimize
    
    Returns:
        Optimized DataFrame
    """
    for col in df.columns:
        col_type = df[col].dtype
        
        if col_type == 'int64':
            df[col] = df[col].astype('int32')
        elif col_type == 'float64':
            df[col] = df[col].astype('float32')
    
    return df


def fragment_expensive_ui(func: Callable) -> Callable:
    """
    Decorator to mark UI function as fragment (Streamlit 1.36+).
    Fragments isolate reruns to specific components.
    
    Usage:
        @fragment_expensive_ui
        def render_complex_chart():
            ...
    """
    try:
        # Streamlit 1.36+ has st.fragment
        return st.fragment(func)
    except AttributeError:
        # Fall back to regular function if st.fragment not available
        return func
