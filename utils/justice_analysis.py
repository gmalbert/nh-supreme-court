"""
Enhanced justice agreement analysis: pairwise matrices, coalitions, trends over time.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional


def calculate_pairwise_agreement(opinions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate pairwise agreement rates between justices.
    
    Args:
        opinions_df: Opinions DataFrame with vote data
    
    Returns:
        DataFrame with justice pairs and agreement rates
    """
    # Extract votes from opinions
    # Assumes vote data is in format like: "MacDonald, Hicks, Bassett (majority); Donovan (dissent)"
    
    if "votes" not in opinions_df.columns and "vote_summary" not in opinions_df.columns:
        return pd.DataFrame()
    
    vote_col = "vote_summary" if "vote_summary" in opinions_df.columns else "votes"
    
    # Build agreement matrix
    justices = set()
    agreements = []
    
    for _, row in opinions_df.iterrows():
        vote_text = row.get(vote_col, "")
        if not vote_text or pd.isna(vote_text):
            continue
        
        # Parse majority and dissent
        # This is a simplified parser - actual implementation should use vote_parser.py
        if "(" in vote_text:
            parts = vote_text.split(";")
            majority = []
            dissent = []
            concurrence = []
            
            for part in parts:
                if "dissent" in part.lower():
                    names = part.split("(")[0].strip().split(",")
                    dissent.extend([n.strip() for n in names if n.strip()])
                elif "concur" in part.lower():
                    names = part.split("(")[0].strip().split(",")
                    concurrence.extend([n.strip() for n in names if n.strip()])
                else:
                    names = part.split("(")[0].strip().split(",")
                    majority.extend([n.strip() for n in names if n.strip()])
            
            # Record agreements
            all_justices = majority + dissent + concurrence
            justices.update(all_justices)
            
            # Majority agrees with each other
            for i, j1 in enumerate(majority):
                for j2 in majority[i+1:]:
                    agreements.append({"justice1": j1, "justice2": j2, "agreed": True})
            
            # Dissent agrees with each other
            for i, j1 in enumerate(dissent):
                for j2 in dissent[i+1:]:
                    agreements.append({"justice1": j1, "justice2": j2, "agreed": True})
            
            # Majority disagrees with dissent
            for j1 in majority:
                for j2 in dissent:
                    agreements.append({"justice1": j1, "justice2": j2, "agreed": False})
    
    if not agreements:
        return pd.DataFrame()
    
    # Calculate agreement rates
    agreements_df = pd.DataFrame(agreements)
    
    # Group by justice pair
    grouped = agreements_df.groupby(["justice1", "justice2"]).agg({
        "agreed": ["sum", "count"]
    }).reset_index()
    
    grouped.columns = ["justice1", "justice2", "agreed_count", "total_count"]
    grouped["agreement_rate"] = grouped["agreed_count"] / grouped["total_count"] * 100
    
    return grouped


def build_agreement_matrix(pairwise_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build symmetric agreement matrix from pairwise data.
    
    Args:
        pairwise_df: DataFrame with justice pairs and agreement rates
    
    Returns:
        Symmetric DataFrame with justices as rows and columns
    """
    if pairwise_df.empty:
        return pd.DataFrame()
    
    # Get all justices
    justices = sorted(set(pairwise_df["justice1"].unique()) | set(pairwise_df["justice2"].unique()))
    
    # Initialize matrix
    matrix = pd.DataFrame(
        np.nan,
        index=justices,
        columns=justices,
    )
    
    # Fill matrix (symmetric)
    for _, row in pairwise_df.iterrows():
        j1 = row["justice1"]
        j2 = row["justice2"]
        rate = row["agreement_rate"]
        
        matrix.loc[j1, j2] = rate
        matrix.loc[j2, j1] = rate
    
    # Diagonal is 100% (justice agrees with self)
    for j in justices:
        matrix.loc[j, j] = 100.0
    
    return matrix


def identify_coalitions(agreement_matrix: pd.DataFrame, threshold: float = 80.0) -> list[set]:
    """
    Identify justice coalitions based on high agreement rates.
    
    Args:
        agreement_matrix: Symmetric agreement matrix
        threshold: Agreement rate threshold for coalition membership
    
    Returns:
        List of coalition sets
    """
    if agreement_matrix.empty:
        return []
    
    coalitions = []
    processed = set()
    
    for justice in agreement_matrix.index:
        if justice in processed:
            continue
        
        # Find justices with high agreement
        high_agreement = agreement_matrix.loc[justice]
        high_agreement = high_agreement[high_agreement >= threshold]
        
        coalition = set(high_agreement.index)
        
        if len(coalition) > 1:
            coalitions.append(coalition)
            processed.update(coalition)
    
    return coalitions


def calculate_agreement_over_time(
    opinions_df: pd.DataFrame,
    justice1: str,
    justice2: str,
) -> pd.DataFrame:
    """
    Calculate agreement rate between two justices over time.
    
    Args:
        opinions_df: Opinions DataFrame
        justice1: First justice name
        justice2: Second justice name
    
    Returns:
        DataFrame with year and agreement rate
    """
    if "date_issued" not in opinions_df.columns:
        return pd.DataFrame()
    
    opinions_df["date_issued"] = pd.to_datetime(opinions_df["date_issued"], errors="coerce")
    opinions_df["year"] = opinions_df["date_issued"].dt.year
    
    yearly_agreements = []
    
    for year in sorted(opinions_df["year"].dropna().unique()):
        year_df = opinions_df[opinions_df["year"] == year]
        
        pairwise = calculate_pairwise_agreement(year_df)
        
        if not pairwise.empty:
            # Find this pair
            pair_data = pairwise[
                ((pairwise["justice1"] == justice1) & (pairwise["justice2"] == justice2)) |
                ((pairwise["justice1"] == justice2) & (pairwise["justice2"] == justice1))
            ]
            
            if not pair_data.empty:
                yearly_agreements.append({
                    "year": year,
                    "agreement_rate": pair_data.iloc[0]["agreement_rate"],
                    "cases": pair_data.iloc[0]["total_count"],
                })
    
    return pd.DataFrame(yearly_agreements)


def calculate_median_voter(agreement_matrix: pd.DataFrame) -> Optional[str]:
    """
    Identify the median voter (justice with highest average agreement across all others).
    
    Args:
        agreement_matrix: Symmetric agreement matrix
    
    Returns:
        Name of median voter justice
    """
    if agreement_matrix.empty:
        return None
    
    # Calculate average agreement for each justice
    avg_agreement = {}
    
    for justice in agreement_matrix.index:
        # Exclude self-agreement (100%)
        agreements = agreement_matrix.loc[justice].drop(justice)
        avg_agreement[justice] = agreements.mean()
    
    # Return justice with highest average
    if avg_agreement:
        return max(avg_agreement, key=avg_agreement.get)
    
    return None


def calculate_dissent_rate_by_author(opinions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate dissent rate by opinion author.
    Shows which authors write opinions that attract dissents.
    
    Args:
        opinions_df: Opinions DataFrame
    
    Returns:
        DataFrame with author and dissent rate
    """
    if "author" not in opinions_df.columns or "dissent" not in opinions_df.columns:
        return pd.DataFrame()
    
    grouped = opinions_df.groupby("author").agg({
        "dissent": ["sum", "count"]
    }).reset_index()
    
    grouped.columns = ["author", "dissent_count", "total_count"]
    grouped["dissent_rate"] = grouped["dissent_count"] / grouped["total_count"] * 100
    
    return grouped.sort_values("dissent_rate", ascending=False)
