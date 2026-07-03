"""
Similar-cases recommender using TF-IDF, topic overlap, RSA citations, and citation graphs.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def calculate_similarity_scores(
    target_case: dict[str, Any],
    candidate_cases: pd.DataFrame,
    citation_graph: Optional[dict] = None,
) -> list[dict[str, Any]]:
    """
    Calculate similarity scores between target case and candidates.
    
    Args:
        target_case: Dict with target case metadata (case_number, topics, rsa_citations, summary, full_text)
        candidate_cases: DataFrame with candidate cases
        citation_graph: Optional dict mapping case_number -> list of cited cases
    
    Returns:
        List of dicts with case info and similarity scores
    """
    results = []
    
    target_topics = set(target_case.get("topics", []))
    target_rsa = set(target_case.get("rsa_citations", []))
    target_text = target_case.get("full_text", "") + " " + target_case.get("summary", "")
    
    for _, candidate in candidate_cases.iterrows():
        case_number = candidate["case_number"]
        
        # Skip if it's the target case itself
        if case_number == target_case.get("case_number"):
            continue
        
        # Topic overlap score (0-1)
        candidate_topics = set(candidate.get("topics", []) if isinstance(candidate.get("topics"), list) else [])
        topic_overlap = len(target_topics & candidate_topics) / max(len(target_topics | candidate_topics), 1)
        
        # RSA overlap score (0-1)
        candidate_rsa = set(candidate.get("rsa_citations", []) if isinstance(candidate.get("rsa_citations"), list) else [])
        rsa_overlap = len(target_rsa & candidate_rsa) / max(len(target_rsa | candidate_rsa), 1)
        
        # Citation relationship score (0-1)
        citation_score = 0.0
        if citation_graph:
            target_cites = set(citation_graph.get(target_case.get("case_number"), []))
            candidate_cites = set(citation_graph.get(case_number, []))
            
            # Direct citation
            if case_number in target_cites or target_case.get("case_number") in candidate_cites:
                citation_score = 1.0
            # Shared citations
            elif target_cites and candidate_cites:
                citation_score = len(target_cites & candidate_cites) / max(len(target_cites | candidate_cites), 1) * 0.5
        
        # Combined score (weighted average)
        similarity_score = (
            topic_overlap * 0.35 +
            rsa_overlap * 0.25 +
            citation_score * 0.40
        )
        
        # Reason for recommendation
        reasons = []
        if topic_overlap > 0.3:
            shared_topics = list(target_topics & candidate_topics)[:3]
            reasons.append(f"Shared topics: {', '.join(shared_topics)}")
        if rsa_overlap > 0.2:
            shared_rsa = list(target_rsa & candidate_rsa)[:2]
            reasons.append(f"Shared statutes: {', '.join(shared_rsa)}")
        if citation_score > 0.5:
            reasons.append("Direct or related citations")
        
        if similarity_score > 0:
            results.append({
                "case_number": case_number,
                "case_name": candidate.get("case_name", ""),
                "citation": candidate.get("citation", ""),
                "year": candidate.get("citation_year"),
                "outcome": candidate.get("outcome", ""),
                "similarity_score": similarity_score,
                "reasons": reasons,
            })
    
    # Sort by similarity score descending
    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    
    return results


def find_similar_cases(
    case_number: str,
    opinions_df: pd.DataFrame,
    opinion_texts: Optional[dict[str, str]] = None,
    citation_graph: Optional[dict] = None,
    limit: int = 5,
    exclude_future: bool = True,
) -> list[dict[str, Any]]:
    """
    Find similar cases to the given case.
    
    Args:
        case_number: Target case number
        opinions_df: DataFrame with all opinions
        opinion_texts: Optional dict mapping case_number to full text
        citation_graph: Optional dict of citation relationships
        limit: Number of similar cases to return
        exclude_future: If True, only return cases before the target case
    
    Returns:
        List of similar cases with scores and reasons
    """
    # Find target case
    target_row = opinions_df[opinions_df["case_number"] == case_number]
    if target_row.empty:
        return []
    
    target = target_row.iloc[0].to_dict()
    
    # Add full text if available
    if opinion_texts and case_number in opinion_texts:
        target["full_text"] = opinion_texts[case_number]
    else:
        target["full_text"] = ""
    
    # Filter candidates
    candidates = opinions_df.copy()
    
    # Exclude future-dated cases if requested
    if exclude_future and "date_issued" in candidates.columns:
        try:
            target_date = pd.to_datetime(target.get("date_issued"), errors="coerce")
            if pd.notna(target_date):
                candidates["date_issued"] = pd.to_datetime(candidates["date_issued"], errors="coerce")
                candidates = candidates[candidates["date_issued"] < target_date]
        except Exception:
            pass  # Skip date filtering if parsing fails
    
    # Exclude the target case itself
    candidates = candidates[candidates["case_number"] != case_number]
    
    if candidates.empty:
        return []
    
    # Calculate similarity
    similar_cases = calculate_similarity_scores(target, candidates, citation_graph)
    
    # Return top N
    return similar_cases[:limit]


def explain_similarity(case1: dict, case2: dict) -> list[str]:
    """
    Generate human-readable explanation of why two cases are similar.
    
    Args:
        case1: First case dict with metadata
        case2: Second case dict with metadata
    
    Returns:
        List of explanation strings
    """
    explanations = []
    
    # Topic similarity
    topics1 = set(case1.get("topics", []))
    topics2 = set(case2.get("topics", []))
    shared_topics = topics1 & topics2
    
    if shared_topics:
        explanations.append(f"Both involve: {', '.join(list(shared_topics)[:3])}")
    
    # RSA similarity
    rsa1 = set(case1.get("rsa_citations", []))
    rsa2 = set(case2.get("rsa_citations", []))
    shared_rsa = rsa1 & rsa2
    
    if shared_rsa:
        explanations.append(f"Both cite: {', '.join(list(shared_rsa)[:2])}")
    
    # Outcome similarity
    if case1.get("outcome") == case2.get("outcome"):
        explanations.append(f"Same outcome: {case1.get('outcome')}")
    
    # Author similarity
    if case1.get("author") == case2.get("author"):
        explanations.append(f"Same author: {case1.get('author')}")
    
    # Court similarity
    if case1.get("lower_court_type") == case2.get("lower_court_type"):
        explanations.append(f"Both from {case1.get('lower_court_type')} Court")
    
    return explanations if explanations else ["Similar legal issues"]
