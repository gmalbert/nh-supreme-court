"""
Multi-source case retrieval for legal chatbox.
Supports Supreme Court, NH Supreme Court, and combined search.
"""

import html
import json
import re
from typing import List, Dict, Optional
from pathlib import Path
import pandas as pd
import streamlit as st
from urllib.parse import quote_plus

# Import existing search for Supreme Court
try:
    from utils.text_search import search as supreme_search, is_available as supreme_available
    SUPREME_SEARCH_AVAILABLE = True
except ImportError:
    SUPREME_SEARCH_AVAILABLE = False


class CaseRetriever:
    """
    Retrieve relevant cases from multiple sources using TF-IDF search.
    """

    def __init__(self, repo_root: Optional[Path] = None):
        """
        Initialize retriever.

        Args:
            repo_root: Path to repository root. Auto-detected if None.
        """
        if repo_root is None:
            # Auto-detect based on current file location
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root)

        # Initialize NH search index (lazy loaded)
        self._nh_vectorizer = None
        self._nh_matrix = None
        self._nh_index_df = None
        self._supreme_detail_by_href = None

    def retrieve_cases(
        self,
        query: str,
        source: str = "supreme-court",
        top_k: int = 5
    ) -> List[Dict]:
        """
        Retrieve relevant cases from specified source(s).

        Args:
            query: Natural language query
            source: "supreme-court", "nh-supreme-court", or "both"
            top_k: Number of cases to retrieve per source

        Returns:
            List of case dicts with keys: name, source, term/year, url, snippet, score
        """
        if source == "supreme-court":
            return self._search_supreme_court(query, top_k)
        elif source == "nh-supreme-court":
            return self._search_nh_court(query, top_k)
        elif source == "both":
            supreme_results = self._search_supreme_court(query, top_k)
            nh_results = self._search_nh_court(query, top_k)

            # Combine and re-rank by score
            combined = supreme_results + nh_results
            combined.sort(key=lambda x: x.get("score", 0), reverse=True)

            return combined[:top_k * 2]  # Return more when searching both
        else:
            raise ValueError(f"Unknown source: {source}")

    def _search_supreme_court(self, query: str, top_k: int) -> List[Dict]:
        """Search US Supreme Court cases."""
        if not SUPREME_SEARCH_AVAILABLE or not supreme_available():
            return [{
                "name": "Error",
                "source": "supreme-court",
                "snippet": "Supreme Court search not available. Check data files.",
                "score": 0
            }]

        try:
            results = supreme_search(query, top_k=top_k)

            # Enhance results with additional data
            enhanced = []
            for r in results:
                case = {
                    "name": r.get("name", "Unknown"),
                    "source": "supreme-court",
                    "term": r.get("term"),
                    "docket_number": r.get("docket_number", ""),
                    "score": r.get("score", 0),
                    "href": r.get("href", ""),
                }

                # Attach bounded, labeled source material for the model. The
                # detail table is loaded once and indexed by href.
                case.update(self._get_supreme_court_detail(r.get("href", "")))

                # Streamlit's browser route is the page slug, not its .py filename.
                case_name = r.get('name', '')
                encoded_name = quote_plus(case_name)
                case["url"] = f"/Cases?q={encoded_name}&case={encoded_name}"

                enhanced.append(case)

            return enhanced

        except Exception as e:
            st.warning(f"Supreme Court search error: {e}")
            return []

    def _search_nh_court(self, query: str, top_k: int) -> List[Dict]:
        """Search NH Supreme Court cases using TF-IDF."""
        # Build index if not already built
        if self._nh_vectorizer is None:
            self._build_nh_index()

        if self._nh_index_df is None or self._nh_index_df.empty:
            return [{
                "name": "Error",
                "source": "nh-supreme-court",
                "snippet": "NH Supreme Court data not available.",
                "score": 0
            }]

        try:
            from sklearn.metrics.pairwise import cosine_similarity

            # ── Exact case-name match (for queries like "State v. Smith") ──
            exact_candidates = []
            if re.search(r'\bv\.?\s+', query, re.I):
                q_lower = re.sub(r'\bv\.?\s+', ' v. ', query, flags=re.I).strip().lower()
                for df_idx in range(len(self._nh_index_df)):
                    cn = str(self._nh_index_df.iloc[df_idx].get("case_name", "")).lower()
                    if q_lower in cn or cn in q_lower:
                        exact_candidates.append((df_idx, 0.999))
                        if len(exact_candidates) >= top_k:
                            break
                if not exact_candidates:
                    for df_idx in range(len(self._nh_index_df)):
                        cn = str(self._nh_index_df.iloc[df_idx].get("case_name", "")).lower()
                        q_words = set(q_lower.split())
                        cn_words = set(cn.split())
                        overlap = q_words & cn_words
                        if len(overlap) >= max(2, len(q_words) // 2):
                            exact_candidates.append((df_idx, 0.9))

            q_vec = self._nh_vectorizer.transform([query.lower()])
            scores = cosine_similarity(q_vec, self._nh_matrix).flatten()
            top_idx = scores.argsort()[::-1][:top_k]

            results = []
            seen_idxs = set()
            # Prepend exact matches
            for df_idx, boost in exact_candidates:
                if df_idx in seen_idxs:
                    continue
                seen_idxs.add(df_idx)
                scores[df_idx] = max(scores[df_idx], boost)

            top_idx = scores.argsort()[::-1][:top_k]
            for i in top_idx:
                score = float(scores[i])
                if score < 0.01:
                    break

                row = self._nh_index_df.iloc[i]

                def _v(key: str, default: str = "") -> str:
                    val = row.get(key, default)
                    if isinstance(val, float) and pd.isna(val):
                        return default
                    return str(val)

                case_number = _v("case_number")
                summary = _v("summary_paragraph")
                outcome_raw = _v("outcome")
                outcome = outcome_raw.replace("_", " ").title() if outcome_raw and outcome_raw != "nan" else ""

                # Load full opinion text and combine with summary
                full_text_path = self.repo_root.parent / "nh-supreme-court" / "data" / "processed" / "text" / f"{case_number}.txt"
                full_text = ""
                if full_text_path.exists():
                    full_text = full_text_path.read_text(encoding="utf-8", errors="replace")[:2000]
                combined = (summary + "\n\n" + full_text).strip()
                narrative = self._truncate_text(combined, 2500)
                case = {
                    "name": _v("case_name", "Unknown"),
                    "source": "nh-supreme-court",
                    "year": _v("term_year"),
                    "docket_number": case_number,
                    "href": case_number,
                    "score": round(score, 4),
                    "snippet": self._truncate_text(summary, 300),
                    "outcome": outcome,
                    "author": _v("author"),
                    "facts": narrative,
                    "facts_of_the_case": narrative,
                    "holding": outcome + " — " + narrative[:300] if outcome else narrative,
                    "conclusion": outcome + " — " + narrative[:300] if outcome else narrative,
                    "description": self._truncate_text(combined, 500),
                }

                # Link to Case Explorer with case number
                case["url"] = f"/case-explorer?case={case_number}"

                results.append(case)

            return results

        except Exception as e:
            st.warning(f"NH Court search error: {e}")
            return []

    def _build_nh_index(self):
        """Build TF-IDF index for NH Supreme Court opinions."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            # Try to load opinions data from NH repo (if accessible)
            # This will only work if both repos are in the workspace
            parent_dir = self.repo_root.parent
            nh_opinions_path = parent_dir / "nh-supreme-court" / "data" / "processed" / "opinions.csv"

            if not nh_opinions_path.exists():
                # Try relative path if workspace structure is different
                return

            df = pd.read_csv(nh_opinions_path)

            # Pre-load full opinion texts
            text_dir = nh_opinions_path.parent / "text"
            full_texts: dict[str, str] = {}
            if text_dir.exists():
                for fp in text_dir.iterdir():
                    if fp.suffix == ".txt":
                        full_texts[fp.stem] = fp.read_text(encoding="utf-8", errors="replace")

            # Combine text fields for search
            def _combine_text(row):
                parts = [
                    str(row.get("case_name", "")),
                    str(row.get("summary_paragraph", "")),
                    str(row.get("rsa_citations", "")),
                    str(row.get("outcome", "")),
                    full_texts.get(str(row.get("case_number", "")), ""),
                ]
                return " ".join(p for p in parts if p and p != "nan").lower()

            df["_search_text"] = df.apply(_combine_text, axis=1)
            df = df[df["_search_text"].str.len() > 20].reset_index(drop=True)

            # Build vectorizer and matrix
            vectorizer = TfidfVectorizer(
                max_features=20_000,
                ngram_range=(1, 2),
                min_df=2,
                sublinear_tf=True,
                stop_words="english",
            )

            matrix = vectorizer.fit_transform(df["_search_text"])

            self._nh_vectorizer = vectorizer
            self._nh_matrix = matrix
            self._nh_index_df = df

        except Exception as e:
            # Silently fail - NH search just won't be available
            pass

    @staticmethod
    def _clean_text(value) -> str:
        """Return plain text without leaking missing-value sentinels."""
        if value is None or pd.isna(value):
            return ""
        text = html.unescape(re.sub(r"<[^>]+>", " ", str(value)))
        return re.sub(r"\s+", " ", text).strip()

    def _load_supreme_court_details(self) -> Dict[str, Dict]:
        if self._supreme_detail_by_href is not None:
            return self._supreme_detail_by_href

        self._supreme_detail_by_href = {}
        try:
            detail_path = self.repo_root / "data" / "case_detail.parquet"
            if not detail_path.exists():
                return self._supreme_detail_by_href

            columns = ["href", "facts_of_the_case", "question", "conclusion", "description", "decisions"]
            df = pd.read_parquet(detail_path, columns=columns)
            self._supreme_detail_by_href = {
                row["href"]: row.to_dict()
                for _, row in df.iterrows()
                if self._clean_text(row.get("href"))
            }
        except Exception:
            pass
        return self._supreme_detail_by_href

    def _get_supreme_court_detail(self, href: str) -> Dict[str, str]:
        """Get clean, bounded fields from a Supreme Court case detail."""
        row = self._load_supreme_court_details().get(href, {})
        facts = self._clean_text(row.get("facts_of_the_case"))
        question = self._clean_text(row.get("question"))
        holding = self._clean_text(row.get("conclusion"))
        description = self._clean_text(row.get("description"))
        detail = {
            "facts": self._truncate_text(facts, 900),
            "question": self._truncate_text(question, 500),
            "holding": self._truncate_text(holding, 900),
            "description": self._truncate_text(description, 500),
            "snippet": self._truncate_text(facts or question or description, 300),
        }
        detail.update(self._summarize_decisions(row.get("decisions")))
        return detail

    @staticmethod
    def _summarize_decisions(value) -> Dict[str, str]:
        """Extract a compact vote split and justice alignment from Oyez data."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return {}
        try:
            decisions = json.loads(value) if isinstance(value, str) else value
        except (TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(decisions, (list, tuple)):
            return {}

        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            votes = decision.get("votes") or []
            majority, minority = [], []
            opinion_authors = []
            majority_authors, dissent_authors, concurrence_authors = [], [], []
            for vote in votes:
                if not isinstance(vote, dict):
                    continue
                name = (vote.get("member") or {}).get("name")
                side = (vote.get("vote") or "").lower()
                opinion_type = (vote.get("opinion_type") or "").lower()
                if not name:
                    continue
                if side in ("majority", "concurrence"):
                    majority.append(name)
                elif side in ("minority", "dissent"):
                    minority.append(name)
                if opinion_type not in ("", "none"):
                    opinion_authors.append(f"{opinion_type}: {name}")
                    if opinion_type in ("majority", "plurality"):
                        majority_authors.append(name)
                    elif "dissent" in opinion_type:
                        dissent_authors.append(name)
                    elif "concurr" in opinion_type:
                        concurrence_authors.append(name)
            if majority or minority:
                summary = {
                    "vote_split": f"{len(majority)}-{len(minority)}",
                    "majority_justices": ", ".join(majority),
                    "minority_justices": ", ".join(minority),
                }
                if opinion_authors:
                    summary["opinion_authors"] = "; ".join(opinion_authors)
                if majority_authors:
                    summary["majority_opinion_authors"] = ", ".join(majority_authors)
                if dissent_authors:
                    summary["dissent_authors"] = ", ".join(dissent_authors)
                if concurrence_authors:
                    summary["concurrence_authors"] = ", ".join(concurrence_authors)
                return summary
        return {}

    def _get_supreme_court_snippet(self, href: str) -> str:
        """Backward-compatible snippet accessor used by older tests/callers."""
        return self._get_supreme_court_detail(href)["snippet"]

    def _truncate_text(self, text: str, max_chars: int) -> str:
        """Truncate text to max_chars, breaking at sentence boundary."""
        if not text or len(text) <= max_chars:
            return text

        truncated = text[:max_chars]

        # Try to break at sentence
        last_period = truncated.rfind(". ")
        if last_period > max_chars * 0.7:  # Only if we don't lose too much
            return truncated[:last_period + 1]

        return truncated + "..."

    def format_context_for_llm(self, cases: List[Dict]) -> str:
        """
        Format retrieved cases as context for LLM.

        Args:
            cases: List of case dicts from retrieve_cases()

        Returns:
            Formatted text context
        """
        if not cases:
            return "No relevant cases found."

        context_parts = []

        for i, case in enumerate(cases, 1):
            source_label = "U.S. Supreme Court" if case["source"] == "supreme-court" else "NH Supreme Court"

            # Build case entry
            entry = f"**Case {i}: {case['name']}**\n"
            entry += f"Court: {source_label}\n"

            if case.get("term"):
                entry += f"Term: {case['term']}\n"
            elif case.get("year"):
                entry += f"Year: {case['year']}\n"

            if case.get("docket_number"):
                entry += f"Docket: {case['docket_number']}\n"

            if case.get("outcome"):
                entry += f"Outcome: {case['outcome']}\n"

            if case.get("facts"):
                entry += f"\nFacts: {case['facts']}\n"
            if case.get("question"):
                entry += f"Question: {case['question']}\n"
            entry += f"Holding: {case.get('holding') or 'Not available in the supplied case record.'}\n"
            if case.get("vote_split"):
                entry += f"Vote split: {case['vote_split']}\n"
            if case.get("majority_justices"):
                entry += f"Majority: {case['majority_justices']}\n"
            if case.get("minority_justices"):
                entry += f"Minority/dissent: {case['minority_justices']}\n"
            if case.get("opinion_authors"):
                entry += f"Opinion author(s): {case['opinion_authors']}\n"
            if case.get("majority_opinion_authors"):
                entry += f"Majority/plurality opinion author(s): {case['majority_opinion_authors']}\n"
            if case.get("dissent_authors"):
                entry += f"Dissenting opinion author(s): {case['dissent_authors']}\n"
            elif case.get("vote_split"):
                entry += "Dissenting opinion author(s): None identified in the supplied Oyez record.\n"
            if case.get("concurrence_authors"):
                entry += f"Concurring opinion author(s): {case['concurrence_authors']}\n"
            if case.get("description"):
                entry += f"Description: {case['description']}\n"
            elif case.get("snippet") and not case.get("facts"):
                entry += f"Summary: {case['snippet']}\n"

            context_parts.append(entry)

        return "\n\n".join(context_parts)


# Convenience functions
def get_retriever() -> CaseRetriever:
    """Create a retriever instance (index is lazily built)."""
    return CaseRetriever()


def retrieve_cases(query: str, source: str = "supreme-court", top_k: int = 5) -> List[Dict]:
    """Retrieve cases. See CaseRetriever.retrieve_cases for details."""
    retriever = get_retriever()
    return retriever.retrieve_cases(query, source, top_k)


def format_context(cases: List[Dict]) -> str:
    """Format cases for LLM. See CaseRetriever.format_context_for_llm."""
    retriever = get_retriever()
    return retriever.format_context_for_llm(cases)


_REFERENTIAL_PATTERNS = (
    r"\b(?:these|those)\s+(?:cases?|holdings?|decisions?|rules?)\b",
    r"\bthat\s+(?:case|holding|decision|rule)\b",
    r"\bthe\s+(?:dissent|majority|first|second|last)\b",
    r"\blater\s+decisions?\b",
    r"\bhow\s+(?:did|do)\s+(?:it|they|these|those)\b",
)


def is_referential_followup(question: str) -> bool:
    """Conservatively identify a question that depends on prior context."""
    text = question.strip().lower()
    return bool(text) and any(re.search(pattern, text) for pattern in _REFERENTIAL_PATTERNS)


def build_retrieval_query(
    question: str,
    previous_question: str = "",
    previous_cases: Optional[List[Dict]] = None,
) -> str:
    """Expand only referential follow-ups; preserve standalone queries verbatim."""
    if not is_referential_followup(question):
        return question

    parts = [f"Current question: {question}"]
    if previous_question:
        parts.append(f"Previous topic: {previous_question}")
    case_names = [
        case.get("name", "").strip()
        for case in (previous_cases or [])
        if case.get("name") and case.get("name") != "Error"
    ]
    if case_names:
        parts.append("Cases: " + "; ".join(case_names))
    return "\n".join(parts)


def merge_retrieved_cases(
    newly_retrieved: List[Dict],
    previous_cases: Optional[List[Dict]] = None,
    include_previous: bool = False,
    max_cases: Optional[int] = None,
) -> List[Dict]:
    """Deduplicate cases by href while retaining prior referenced material."""
    candidates = list(previous_cases or []) + list(newly_retrieved) if include_previous else list(newly_retrieved)
    merged = []
    seen = set()
    for case in candidates:
        key = case.get("href") or (case.get("source"), case.get("name"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(case)
        if max_cases is not None and len(merged) >= max_cases:
            break
    return merged
