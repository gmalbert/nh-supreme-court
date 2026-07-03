"""
Full-text opinion search using SQLite FTS5.
Provides ranked search results with highlighted snippets.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SEARCH_INDEX_PATH = ROOT / "data" / "processed" / "opinions_fts.sqlite"


def open_index() -> sqlite3.Connection:
    """Open or create the FTS5 search index."""
    conn = sqlite3.connect(str(SEARCH_INDEX_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def create_index(conn: sqlite3.Connection) -> None:
    """Create the FTS5 virtual table for opinion search."""
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS opinions_fts USING fts5(
            case_number UNINDEXED,
            citation,
            case_name,
            full_text,
            summary,
            topics,
            author,
            outcome,
            year UNINDEXED,
            tokenize = 'porter unicode61'
        )
    """)
    conn.commit()


def index_opinion(
    conn: sqlite3.Connection,
    case_number: str,
    citation: str,
    case_name: str,
    full_text: str,
    summary: str,
    topics: str,
    author: str,
    outcome: str,
    year: int,
) -> None:
    """Add a single opinion to the search index."""
    conn.execute(
        """
        INSERT INTO opinions_fts 
        (case_number, citation, case_name, full_text, summary, topics, author, outcome, year)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (case_number, citation, case_name, full_text, summary, topics, author, outcome, year),
    )


def clear_index(conn: sqlite3.Connection) -> None:
    """Clear all entries from the search index."""
    conn.execute("DELETE FROM opinions_fts")
    conn.commit()


def search(
    query: str,
    conn: Optional[sqlite3.Connection] = None,
    year_filter: Optional[list[int]] = None,
    topic_filter: Optional[list[str]] = None,
    author_filter: Optional[list[str]] = None,
    outcome_filter: Optional[list[str]] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Search the opinion index with optional filters.
    
    Args:
        query: Search query (supports phrases with quotes, AND/OR/NOT operators)
        conn: Database connection (will create if None)
        year_filter: Filter by years
        topic_filter: Filter by topics (partial match)
        author_filter: Filter by author name
        outcome_filter: Filter by outcome
        limit: Maximum results to return
    
    Returns:
        List of matching opinions with BM25 rank scores
    """
    should_close = False
    if conn is None:
        conn = open_index()
        should_close = True
    
    try:
        # Validate index exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='opinions_fts'"
        )
        if not cursor.fetchone():
            return []
        
        # Build WHERE clause for filters
        where_clauses = []
        params = []
        
        if year_filter:
            placeholders = ",".join("?" * len(year_filter))
            where_clauses.append(f"year IN ({placeholders})")
            params.extend(year_filter)
        
        if topic_filter:
            topic_conditions = " OR ".join(["topics LIKE ?"] * len(topic_filter))
            where_clauses.append(f"({topic_conditions})")
            params.extend([f"%{topic}%" for topic in topic_filter])
        
        if author_filter:
            placeholders = ",".join("?" * len(author_filter))
            where_clauses.append(f"author IN ({placeholders})")
            params.extend(author_filter)
        
        if outcome_filter:
            placeholders = ",".join("?" * len(outcome_filter))
            where_clauses.append(f"outcome IN ({placeholders})")
            params.extend(outcome_filter)
        
        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Execute FTS5 search
        sql = f"""
            SELECT 
                case_number,
                citation,
                case_name,
                summary,
                topics,
                author,
                outcome,
                year,
                rank
            FROM opinions_fts
            WHERE opinions_fts MATCH ? AND {where_clause}
            ORDER BY rank
            LIMIT ?
        """
        
        cursor = conn.execute(sql, [query] + params + [limit])
        results = []
        column_names = [description[0] for description in cursor.description]
        
        for row in cursor:
            row_data = dict(row) if isinstance(row, sqlite3.Row) else dict(zip(column_names, row))
            results.append({
                "case_number": row_data["case_number"],
                "citation": row_data["citation"],
                "case_name": row_data["case_name"],
                "summary": row_data["summary"][:500] if row_data["summary"] else "",
                "topics": row_data["topics"],
                "author": row_data["author"],
                "outcome": row_data["outcome"],
                "year": row_data["year"],
                "rank": row_data["rank"],
            })
        
        return results
    
    finally:
        if should_close:
            conn.close()


def get_snippet(text: str, query_terms: list[str], context_chars: int = 150) -> str:
    """
    Extract a snippet from text highlighting query terms.
    
    Args:
        text: Full text to extract snippet from
        query_terms: Terms to highlight
        context_chars: Characters of context on each side
    
    Returns:
        Snippet with highlighted terms
    """
    if not text or not query_terms:
        return text[:300] if text else ""
    
    # Find first occurrence of any query term
    text_lower = text.lower()
    first_pos = -1
    
    for term in query_terms:
        term_lower = term.lower().strip('"')
        pos = text_lower.find(term_lower)
        if pos != -1 and (first_pos == -1 or pos < first_pos):
            first_pos = pos
    
    if first_pos == -1:
        snippet = text[:300]
        return snippet + ("..." if len(text) > len(snippet) else "")
    
    # Extract context around first match
    target_length = min(300, len(text))
    if len(text) > 80:
        target_length = min(target_length, max(60, int(len(text) * 0.8)))
    start = max(0, first_pos - (target_length // 2))
    end = min(len(text), start + target_length)
    start = max(0, end - target_length)
    
    snippet = text[start:end]
    
    # Add ellipsis
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    
    # Highlight terms (case-insensitive)
    for term in query_terms:
        term_clean = term.strip('"')
        pattern = re.compile(re.escape(term_clean), re.IGNORECASE)
        snippet = pattern.sub(lambda m: f"**{m.group()}**", snippet)
    
    return snippet


def rebuild_index(opinions_df: pd.DataFrame, opinion_texts: dict[str, str]) -> int:
    """
    Rebuild the entire search index from opinions DataFrame and text files.
    
    Args:
        opinions_df: DataFrame with opinion metadata
        opinion_texts: Dict mapping case_number to full opinion text
    
    Returns:
        Number of opinions indexed
    """
    conn = open_index()
    
    try:
        # Create table if needed
        create_index(conn)
        
        # Clear existing data
        clear_index(conn)
        
        # Index each opinion
        count = 0
        for _, row in opinions_df.iterrows():
            case_number = row["case_number"]
            full_text = opinion_texts.get(case_number, "")
            
            # Join topics list to string
            topics_str = ", ".join(row.get("topics", [])) if isinstance(row.get("topics"), list) else str(row.get("topics", ""))
            
            index_opinion(
                conn,
                case_number=case_number,
                citation=row.get("citation", ""),
                case_name=row.get("case_name", ""),
                full_text=full_text,
                summary=row.get("summary_paragraph", ""),
                topics=topics_str,
                author=row.get("author", ""),
                outcome=row.get("outcome", ""),
                year=int(row.get("citation_year", 0)) if pd.notna(row.get("citation_year")) else 0,
            )
            count += 1
        
        conn.commit()
        return count
    
    finally:
        conn.close()


def index_exists() -> bool:
    """Check if the search index exists and is not empty."""
    if not SEARCH_INDEX_PATH.exists():
        return False
    
    try:
        conn = open_index()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='opinions_fts'"
        )
        table_exists = cursor.fetchone() is not None
        
        if table_exists:
            cursor = conn.execute("SELECT COUNT(*) FROM opinions_fts")
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
        
        conn.close()
        return False
    except Exception:
        return False
