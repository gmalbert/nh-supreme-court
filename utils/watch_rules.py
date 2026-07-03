"""
Watch rules for tracking new opinions matching user criteria.
Supports keyword, RSA, and topic-based alerts.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd


class WatchRule:
    """Represents a watch rule for opinion alerts."""
    
    def __init__(
        self,
        rule_id: str,
        name: str,
        rule_type: str,  # "keyword", "rsa", "topic"
        criteria: str,
        email: Optional[str] = None,
        created_at: Optional[str] = None,
    ):
        self.rule_id = rule_id
        self.name = name
        self.rule_type = rule_type
        self.criteria = criteria
        self.email = email
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.last_matched: Optional[str] = None
        self.match_count: int = 0
    
    def matches(self, opinion: dict[str, Any]) -> bool:
        """Check if opinion matches this watch rule."""
        if self.rule_type == "keyword":
            # Search in case name, summary, and topics
            search_text = " ".join([
                str(opinion.get("case_name", "")),
                str(opinion.get("summary_paragraph", "")),
                " ".join(opinion.get("topics", [])) if isinstance(opinion.get("topics"), list) else str(opinion.get("topics", "")),
            ]).lower()
            
            return self.criteria.lower() in search_text
        
        elif self.rule_type == "rsa":
            # Check RSA citations
            rsa_citations = opinion.get("rsa_citations", [])
            if isinstance(rsa_citations, list):
                return any(self.criteria.upper() in rsa.upper() for rsa in rsa_citations)
            else:
                return self.criteria.upper() in str(rsa_citations).upper()
        
        elif self.rule_type == "topic":
            # Check topics
            topics = opinion.get("topics", [])
            if isinstance(topics, list):
                return any(self.criteria.lower() in topic.lower() for topic in topics)
            else:
                return self.criteria.lower() in str(topics).lower()
        
        return False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "rule_type": self.rule_type,
            "criteria": self.criteria,
            "email": self.email,
            "created_at": self.created_at,
            "last_matched": self.last_matched,
            "match_count": self.match_count,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "WatchRule":
        """Create WatchRule from dictionary."""
        rule = cls(
            rule_id=data["rule_id"],
            name=data["name"],
            rule_type=data["rule_type"],
            criteria=data["criteria"],
            email=data.get("email"),
            created_at=data.get("created_at"),
        )
        rule.last_matched = data.get("last_matched")
        rule.match_count = data.get("match_count", 0)
        return rule


def load_watch_rules(rules_file: Path) -> list[WatchRule]:
    """Load watch rules from file."""
    if not rules_file.exists():
        return []
    
    try:
        with open(rules_file) as f:
            data = json.load(f)
            return [WatchRule.from_dict(r) for r in data]
    except Exception as e:
        print(f"Error loading watch rules: {e}")
        return []


def save_watch_rules(rules: list[WatchRule], rules_file: Path) -> None:
    """Save watch rules to file."""
    try:
        with open(rules_file, "w") as f:
            json.dump([r.to_dict() for r in rules], f, indent=2)
    except Exception as e:
        print(f"Error saving watch rules: {e}")


def evaluate_rules(
    rules: list[WatchRule],
    new_opinions: pd.DataFrame,
    seen_cases: set[str],
) -> dict[str, list[dict]]:
    """
    Evaluate watch rules against new opinions.
    
    Args:
        rules: List of watch rules to evaluate
        new_opinions: DataFrame with new opinions
        seen_cases: Set of case numbers already seen (for deduplication)
    
    Returns:
        Dict mapping rule_id to list of matching opinions
    """
    matches = {rule.rule_id: [] for rule in rules}
    
    for _, opinion in new_opinions.iterrows():
        case_number = opinion["case_number"]
        
        # Skip if already seen
        if case_number in seen_cases:
            continue
        
        opinion_dict = opinion.to_dict()
        
        # Check each rule
        for rule in rules:
            if rule.matches(opinion_dict):
                matches[rule.rule_id].append({
                    "case_number": case_number,
                    "case_name": opinion.get("case_name", ""),
                    "citation": opinion.get("citation", ""),
                    "date_issued": str(opinion.get("date_issued", "")),
                    "outcome": opinion.get("outcome", ""),
                    "summary": opinion.get("summary_paragraph", "")[:200],
                })
                
                rule.last_matched = datetime.utcnow().isoformat()
                rule.match_count += 1
    
    return matches


def deduplicate_matches(
    current_matches: dict[str, list[dict]],
    seen_file: Path,
) -> dict[str, list[dict]]:
    """
    Remove matches that have already been sent.
    
    Args:
        current_matches: Current rule matches
        seen_file: File tracking sent matches
    
    Returns:
        Deduplicated matches
    """
    # Load seen matches
    seen = set()
    if seen_file.exists():
        try:
            with open(seen_file) as f:
                seen_data = json.load(f)
                seen = set(seen_data)
        except Exception:
            pass
    
    # Filter matches
    deduplicated = {}
    new_seen = []
    
    for rule_id, matches in current_matches.items():
        deduplicated[rule_id] = []
        for match in matches:
            match_key = f"{rule_id}:{match['case_number']}"
            if match_key not in seen:
                deduplicated[rule_id].append(match)
                new_seen.append(match_key)
                seen.add(match_key)
    
    # Save updated seen list
    try:
        with open(seen_file, "w") as f:
            json.dump(list(seen), f)
    except Exception:
        pass
    
    return deduplicated
