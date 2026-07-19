"""Exact case-name, alias, citation, and docket resolution.

The index is built once from a normalized case corpus.  ``search`` returns an
ordered list of RetrievalHit objects whose score encodes both alias
specificity and a penalty for ambiguous one-token parties.
"""

from __future__ import annotations

import re
from collections import defaultdict

import pandas as pd

from .models import RetrievalHit
from .normalize import normalize_case_name, normalize_citation, normalize_docket

_CITATION_RE = re.compile(r"\b\d+\s+U\.S\.\s+\d+\b", re.I)
_DOCKET_RE = re.compile(r"\b(?:No\.\s*)?\d{1,2}-\d{2,5}\b", re.I)

GENERIC_PARTIES = {
    "united", "states", "state", "department", "board", "city", "county",
    "school", "district", "commission", "secretary", "attorney", "general",
    "the", "in", "re", "ex", "parte", "of", "and", "for", "inc", "llc",
    "corp", "company", "co", "ltd", "association", "society", "union",
    "national", "american", "new", "old", "north", "south", "east", "west",
    # Common English adjectives/nouns that also appear as party surnames.
    # Adding these as single-token aliases produces too many false positives
    # in topic questions such as "free speech" or "long arm of the law".
    "free", "long", "short", "young", "old", "near", "far", "high", "low",
    "white", "black", "minor", "major", "people", "good", "bad", "small",
    "great", "little",
}

# Tokens that may appear in legal queries but are not party identifiers.
_QUERY_STOPWORDS = {
    "what", "who", "when", "where", "which", "was", "did", "does", "do",
    "the", "is", "are", "in", "of", "and", "or", "a", "an",
    "case", "court", "decision", "opinion", "holding", "rule", "split",
    "vote", "justice", "judge", "supreme", "issue", "held", "say",
}


class ExactCaseIndex:
    """Resolve full case names, short parties, citations, and dockets."""

    def __init__(self, cases: pd.DataFrame):
        self.cases = cases.reset_index(drop=True)
        self.aliases: dict[str, list[int]] = defaultdict(list)
        self.full_names: dict[str, list[int]] = defaultdict(list)
        self.citations: dict[str, list[int]] = defaultdict(list)
        self.dockets: dict[str, list[int]] = defaultdict(list)
        self._build()

    def _build(self) -> None:
        for idx, row in self.cases.iterrows():
            name_norm = normalize_case_name(str(row.get("name", "")))
            aliases = {name_norm}
            full = name_norm
            if full:
                self.full_names[full].append(idx)

            for party in re.split(r"\s+v\s+", name_norm, maxsplit=1):
                if not party:
                    continue
                # Multi-word parties (e.g. "Board of Education") are matched
                # as whole phrases only — picking a single distinctive token
                # like "major" or "league" produces too many false positives.
                # Single-token parties (e.g. "Pickering", "Garvey") act as
                # both the full party alias and the single-token alias.
                if party in GENERIC_PARTIES:
                    continue
                if len(party) < 4:
                    continue
                aliases.add(party)

            for alias in aliases:
                self.aliases[alias].append(idx)

            citation = normalize_citation(str(row.get("citation", "")))
            docket = normalize_docket(str(row.get("docket_number", "")))
            if citation:
                self.citations[citation].append(idx)
            if docket:
                self.dockets[docket].append(idx)

    @staticmethod
    def _first_distinctive_token(party: str, used_in_name: set[str]) -> str:
        for token in party.split():
            if token in GENERIC_PARTIES:
                continue
            if token in used_in_name:
                continue
            if len(token) < 4:
                continue
            return token
        return ""

    @staticmethod
    def _alias_score(alias: str, indices: list[int]) -> float:
        specificity = min(1.0, 0.55 + len(alias.split()) * 0.12)
        # Soft ambiguity penalty: heavily ambiguous aliases still match but
        # rank below unique ones, leaving fusion to disambiguate via lexical
        # and dense evidence.
        ambiguity_penalty = 1.0 / (1.0 + (len(indices) - 1) * 0.5)
        return specificity * ambiguity_penalty

    def search(self, query: str, limit: int = 10) -> list[RetrievalHit]:
        if not query:
            return []
        normalized_query = normalize_case_name(query)
        # Long topic questions should not trigger single-token alias matches.
        # Only allow full name, citation, and docket hits when the query looks
        # like a topic overview rather than a case lookup.
        token_count = len(normalized_query.split())
        long_query = token_count > 8

        candidates: dict[int, float] = {}

        for citation_match in _CITATION_RE.findall(query):
            citation_norm = normalize_citation(citation_match)
            if citation_norm in self.citations:
                for idx in self.citations[citation_norm]:
                    candidates[idx] = max(candidates.get(idx, 0.0), 1.0)

        for docket_match in _DOCKET_RE.findall(query):
            docket_norm = normalize_docket(docket_match)
            if docket_norm in self.dockets:
                for idx in self.dockets[docket_norm]:
                    candidates[idx] = max(candidates.get(idx, 0.0), 1.0)

        full_match = normalized_query in self.full_names
        if full_match:
            for idx in self.full_names[normalized_query]:
                candidates[idx] = max(candidates.get(idx, 0.0), 1.0)

        if (not long_query) and normalized_query and any(
            token not in _QUERY_STOPWORDS and len(token) >= 3
            for token in normalized_query.split()
        ):
            for alias, indices in self.aliases.items():
                if not alias:
                    continue
                pat = rf"(?:^|\b){re.escape(alias)}(?:$|\b)"
                if re.search(pat, normalized_query):
                    score = self._alias_score(alias, indices)
                    for idx in indices:
                        candidates[idx] = max(candidates.get(idx, 0.0), score)

        ranked = sorted(candidates.items(), key=lambda item: item[1], reverse=True)
        return [
            RetrievalHit(
                document_id=str(self.cases.iloc[idx]["case_id"]),
                case_id=str(self.cases.iloc[idx]["case_id"]),
                source="exact",
                rank=rank,
                score=float(score),
                backend="exact_name",
                text=str(self.cases.iloc[idx].get("name", "")),
                metadata=self.cases.iloc[idx].to_dict(),
            )
            for rank, (idx, score) in enumerate(ranked[:limit], start=1)
            if score > 0
        ]