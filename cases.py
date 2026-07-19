"""
cases.py — Granite State Appeals app entrypoint with Streamlit navigation.
"""

from __future__ import annotations

import ast
import base64
import importlib
import os
import re
import sys
from datetime import date
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote
import json

from dotenv import load_dotenv
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
CITATION_OVERRIDES_PATH = ROOT / "data" / "citation_overrides.json"

# Load environment variables for API keys
load_dotenv(ROOT / ".env")

from utils.constants import APP_NAME, APP_TAGLINE, OUTCOME_COLORS, OUTCOME_LABELS, VOTE_COLORS
try:
    from utils.data_loader import (
        data_last_updated,
        load_attorney_statistics,
        load_brief_counsel,
        load_oral_argument,
        load_opinion_text,
        load_opinions,
        load_opinions_json,
    )
except KeyError:
    # Defensive recovery for intermittent import-state races during Streamlit reloads.
    sys.modules.pop("utils.data_loader", None)
    _data_loader = importlib.import_module("utils.data_loader")
    data_last_updated = _data_loader.data_last_updated
    load_attorney_statistics = _data_loader.load_attorney_statistics
    load_brief_counsel = _data_loader.load_brief_counsel
    load_oral_argument = _data_loader.load_oral_argument
    load_opinion_text = _data_loader.load_opinion_text
    load_opinions = _data_loader.load_opinions
    load_opinions_json = _data_loader.load_opinions_json
from utils.charts import bench_diagram
from utils.justices import normalize_votes_for_bench
from utils.opinion_search import search as fts_search, get_snippet
from footer import add_gavel_glimpse_footer

# Chat module imports
from utils.chat_retriever import (
    build_retrieval_query,
    format_context,
    is_referential_followup,
    merge_retrieved_cases,
    retrieve_cases,
)
from utils.chat_formatter import format_with_links, render_sources, render_follow_ups
from utils.chat_provider import generate_chat_response

# Streamlit page config must be declared once in the entrypoint when using st.navigation.
st.set_page_config(
    page_title=APP_NAME,
    page_icon="⚖️",
    layout="wide",
)


def _render_brand_header(subtitle: str | None = None) -> None:
    logo_path = ROOT / "data_files" / "logo.png"
    col_logo, col_title = st.columns([2, 8])
    with col_logo:
        if logo_path.exists():
            st.image(str(logo_path), width=220)
    with col_title:
        st.title(APP_NAME)
        st.caption(subtitle or APP_TAGLINE)


def _style_dashboard() -> None:
    st.markdown(
        """
        <style>
        .gsa-card {
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 1rem;
            min-height: 132px;
            background: #FFFFFF;
            /* Streamlit sets headings to a light color in dark mode. These
               cards intentionally retain a light surface, so reset their
               inherited foreground color as well. */
            color: #1F2937;
        }
        .gsa-card h3 {
            color: #1F2937;
            margin: 0 0 0.35rem 0;
            font-size: 1.12rem;
        }
        .gsa-card h3 .gsa-card-icon {
            display: inline-block;
            margin-right: 0.35rem;
        }
        .gsa-card p {
            color: #5F6673;
            margin: 0 0 0.8rem 0;
            line-height: 1.45;
        }
        .gsa-nav-card {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 168px;
        }
        .gsa-card-button {
            border: 1px solid #D1D5DB;
            border-radius: 8px;
            color: #2F3440;
            display: block;
            font-weight: 600;
            margin-top: 0.8rem;
            padding: 0.55rem 0.75rem;
            text-align: center;
            text-decoration: none;
            width: 100%;
        }
        .gsa-card-button:hover {
            background: #F8FAFC;
            border-color: #AEB7C2;
            text-decoration: none;
        }
        .gsa-stat {
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 0.9rem 1rem;
            background: #F8FAFC;
        }
        .gsa-stat-label {
            color: #697281;
            font-size: 0.82rem;
            font-weight: 700;
            text-transform: uppercase;
        }
        .gsa-stat-value {
            color: #1F2937;
            font-size: 1.75rem;
            font-weight: 800;
            line-height: 1.2;
        }
        .gsa-chip {
            display: inline-block;
            background: #E7F0F8;
            color: #003057;
            border-radius: 999px;
            padding: 0.18rem 0.55rem;
            margin: 0.15rem 0.25rem 0.15rem 0;
            font-size: 0.78rem;
            font-weight: 700;
            text-decoration: none;
        }
        .gsa-chip:hover {
            background: #D6E8F5;
            text-decoration: underline;
        }
        .gsa-on-this-day {
            align-items: center;
            display: grid;
            gap: 1rem;
            grid-template-columns: 180px minmax(0, 1fr);
            min-height: 0;
        }
        .gsa-on-this-day img {
            width: 156px;
        }
        .gsa-on-this-day a {
            color: #003057;
            font-weight: 800;
            text-decoration: none;
        }
        .gsa-on-this-day a:hover {
            text-decoration: underline;
        }
        .gsa-search-result {
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 0.85rem 1rem;
            background: #FFFFFF;
            margin: 0.55rem 0;
        }
        .gsa-search-result a {
            color: #003057;
            font-weight: 800;
            text-decoration: none;
        }
        .gsa-search-result a:hover {
            text-decoration: underline;
        }
        .gsa-meta {
            color: #697281;
            font-size: 0.86rem;
            margin-top: 0.2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _clean_summary_text(value: str) -> str:
    cleaned = str(value).replace("\ufffd", "").strip()
    cleaned = re.sub(r"^\s*[][(){}\"'“”‘’`]+\s*", "", cleaned)
    cleaned = re.sub(r"\s*[][(){}\"'“”‘’`]+\s*$", "", cleaned)
    return cleaned.strip()

_SECTION_HEADER_RE = re.compile(
    r"(?m)^[ \t]*(?:I\.?\s+)?(?:Background|Facts|BACKGROUND|FACTS|"
    r"Discussion|DISCUSSION|Procedural History|Procedural|PROCEDURAL|"
    r"History|HISTORY|Analysis|ANALYSIS|The Facts|The Background)\s*$",
    re.MULTILINE,
)
_AUTHOR_LINE_RE = re.compile(
    r"^(PER CURIAM|[A-Z][A-Z\-]+(?:\s+[A-Z][A-Z\-]+)?,\s+(?:C\.J\.|J\.))[.\s]",
    re.MULTILINE,
)


def _extract_intro_text(text: str) -> str:
    """Return all paragraphs before the first Background/Facts section header."""
    if not text:
        return ""
    m = _AUTHOR_LINE_RE.search(text)
    body = text[m.end():].lstrip() if m else text
    sm = _SECTION_HEADER_RE.search(body)
    intro = body[:sm.start()].strip() if sm else body[:3000].strip()
    intro = re.sub(r"\n{3,}", "\n\n", intro)
    return intro[:4000]


def _extract_appearance_block(text: str) -> str:
    """Return counsel appearances from the opinion header."""
    if not text:
        return ""

    lines = [line.strip() for line in text.splitlines()]
    start_index = None
    for index, line in enumerate(lines[:80]):
        if line.startswith("Opinion Issued:"):
            start_index = index + 1
            break
    if start_index is None:
        return ""

    block: list[str] = []
    for line in lines[start_index:80]:
        if not line:
            if block:
                block.append("")
            continue
        if _AUTHOR_LINE_RE.match(line):
            break
        if line.startswith(("I.", "II.")):
            break
        block.append(line)

    paragraphs: list[str] = []
    current: list[str] = []
    for line in block:
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(line)
        joined = " ".join(current).lower()
        if re.search(r"\bfor\s+the\b.+\.$", joined):
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))

    return "\n\n".join(paragraphs)


def _render_appearance_block(text: str) -> None:
    appearance = _extract_appearance_block(text)
    if not appearance:
        return

    attorney_data = load_attorney_statistics()
    known_attorneys = {
        attorney["attorney_name"]
        for attorney in attorney_data.get("attorney_stats", [])
        if attorney.get("attorney_name")
    }

    rows = []
    for paragraph in appearance.split("\n\n"):
        side_match = re.search(r",\s+for\s+(?:the\s+)?(.+?)\.$", paragraph, flags=re.IGNORECASE)
        side = side_match.group(1).strip().capitalize() if side_match else "Other"
        participants = []
        for parenthetical in re.findall(r"\(([^)]+)\)", paragraph):
            if not re.search(r"\b(on the brief|on the briefs|orally|on the memorandum)\b", parenthetical, re.IGNORECASE):
                continue
            participant = re.split(
                r",?\s+(?:on the brief|on the briefs|orally|on the memorandum)\b",
                parenthetical,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()
            participant = re.sub(
                r",\s*(?:senior\s+)?(?:assistant\s+)?(?:attorney general|solicitor general|general counsel|attorney).*$",
                "",
                participant,
                flags=re.IGNORECASE,
            ).strip()
            if participant:
                participants.append(participant)
        if participants:
            rows.append({"side": side, "participants": participants})

    st.markdown("**Counsel**")
    if rows:
        for row in rows:
            for name in row["participants"]:
                profile_url = f"/attorney-profile?attorney={quote(name, safe='')}"
                if name in known_attorneys:
                    rendered_name = f"[{escape(name)}]({profile_url})"
                else:
                    rendered_name = escape(name)
                st.markdown(f"- **{escape(row['side'])}:** {rendered_name}")
    else:
        html = "<br><br>".join(escape(line) for line in appearance.split("\n\n"))
        st.markdown(html, unsafe_allow_html=True)
    st.markdown("")


def _as_list(value) -> list[str]:
    try:
        parsed = ast.literal_eval(value) if isinstance(value, str) else value
    except Exception:
        parsed = []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _format_date(value) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return "—"
    return parsed.strftime("%b %d, %Y")


def _display_or_dash(value) -> str:
    """Return a display-safe value for optional scalar metadata."""
    if value is None:
        return "—"
    if pd.isna(value):
        return "—"
    text = str(value).strip()
    return text if text and text.lower() != "nan" else "—"


def _render_case_attorneys(case_number: str) -> None:
    """Render reviewed attorney roster for a linked oral argument, if available."""
    attorney_data = load_attorney_statistics()
    case_attorneys = attorney_data.get("case_attorneys", {}).get(str(case_number), [])
    if not case_attorneys:
        return

    st.markdown("**Oral-argument roster**")
    sides: dict[str, list[dict]] = {}
    for attorney in case_attorneys:
        side = str(attorney.get("side") or "other").capitalize()
        sides.setdefault(side, []).append(attorney)

    for side, attorneys in sides.items():
        st.markdown(f"_{side}_")
        for attorney in attorneys:
            name = str(attorney.get("name") or "Unknown")
            firm = str(attorney.get("firm") or "").strip()
            profile_url = f"/attorney-profile?attorney={quote(name, safe='')}"
            label = f"[{escape(name)}]({profile_url})"
            if firm:
                label += f" ({escape(firm)})"
            st.markdown(f"- {label}")


def _render_case_brief_counsel(case_number: str) -> bool:
    """Render separately generated brief counsel from official decisions."""
    counsel = load_brief_counsel().get(str(case_number), [])
    if not counsel:
        return False
    st.markdown("**Brief counsel**")
    sides: dict[str, list[str]] = {}
    for fact in counsel:
        name = str(fact.get("attorney_raw") or "").strip()
        if name:
            sides.setdefault(str(fact.get("side") or "other").capitalize(), []).append(name)
    for side, names in sides.items():
        for name in dict.fromkeys(names):
            profile_url = f"/attorney-profile?attorney={quote(name, safe='')}"
            st.markdown(f"- **{escape(side)}:** [{escape(name)}]({profile_url})")
    st.markdown("")
    return True


@lru_cache(maxsize=1)
def _load_citation_overrides() -> dict:
    if not CITATION_OVERRIDES_PATH.exists():
        return {}
    try:
        with open(CITATION_OVERRIDES_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _citation_sort_key(value: str) -> int:
    """Rank citation forms for display: reporter, public-domain, case number."""
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{3,5}", text):
        return 2
    if re.fullmatch(r"20\d{2}\s+N\.H\.\s+\d+", text, flags=re.IGNORECASE):
        return 1
    if re.fullmatch(r"\d+\s+N\.H\.\s+\d+", text, flags=re.IGNORECASE):
        return 0
    return 1


def _case_citation_display(row, full_rec: dict | None = None) -> str:
    """Return the best available citation label for a case."""
    candidates = []
    sources = [row]
    if full_rec:
        sources.append(full_rec)

    case_number = _display_or_dash(row.get("case_number") if hasattr(row, "get") else None)
    override = _load_citation_overrides().get(case_number)
    if isinstance(override, dict):
        sources.insert(0, override)

    for source in sources:
        for key in ("reporter_citation", "official_citation", "citation"):
            value = _display_or_dash(source.get(key) if hasattr(source, "get") else None)
            if value != "—" and value not in candidates:
                candidates.append(value)

    if case_number != "—" and case_number not in candidates:
        candidates.append(case_number)

    if not candidates:
        return "—"
    return sorted(candidates, key=_citation_sort_key)[0]


def _month_day_label(value) -> str:
    parsed = pd.Timestamp(value)
    return f"{parsed.strftime('%B')} {parsed.day}"


_SEARCH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "had", "has",
    "have", "he", "her", "his", "in", "into", "is", "it", "its", "of", "on",
    "or", "she", "that", "the", "their", "them", "to", "was", "were", "with",
}


def _search_tokens(value: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9:-]{2,}", value.lower())
    return [token for token in tokens if token not in _SEARCH_STOPWORDS]


def _search_blob(row: pd.Series) -> str:
    fields = [
        row.get("case_name", ""),
        row.get("summary_paragraph", ""),
        row.get("topics", ""),
        row.get("rsa_citations", ""),
        row.get("lower_court", ""),
        row.get("case_type", ""),
        row.get("appeal_type", ""),
        row.get("outcome", ""),
        row.get("author_display", ""),
    ]
    return " ".join("" if pd.isna(field) else str(field) for field in fields).lower()


def _search_opinions(df: pd.DataFrame, query: str, limit: int) -> pd.DataFrame:
    """Search opinions using FTS5 full-text search with fallback to simple search."""
    query = query.strip()
    if not query:
        return df.head(0).copy()

    # Try FTS5 search first
    try:
        fts_results = fts_search(query, limit=limit)
        if fts_results:
            # Convert FTS results to DataFrame
            result_cases = [r["case_number"] for r in fts_results]
            result_df = df[df["case_number"].isin(result_cases)].copy()

            # Add rank scores and snippets
            rank_map = {r["case_number"]: r["rank"] for r in fts_results}
            result_df["_score"] = result_df["case_number"].map(rank_map)
            result_df["_issued_at"] = pd.to_datetime(result_df["date_issued"], errors="coerce")

            # Sort by rank (lower is better with BM25)
            return result_df.sort_values(["_score", "_issued_at"], ascending=[True, False])
    except Exception as e:
        # Fall back to simple search if FTS5 fails
        print(f"FTS5 search failed, using fallback: {e}")

    # Fallback: simple token-based search
    tokens = _search_tokens(query)
    if not tokens:
        return df.head(0).copy()

    query_lower = query.lower()
    rows: list[tuple[int, int]] = []
    for idx, row in df.iterrows():
        blob = _search_blob(row)
        score = 0
        if query_lower in blob:
            score += 12
        case_name = str(row.get("case_name", "")).lower()
        summary = str(row.get("summary_paragraph", "")).lower()
        topics = str(row.get("topics", "")).lower()
        rsas = str(row.get("rsa_citations", "")).lower()
        for token in tokens:
            if token in case_name:
                score += 8
            if token in summary:
                score += 4
            if token in topics:
                score += 5
            if token in rsas:
                score += 6
            if token in blob:
                score += 1
        if score:
            rows.append((idx, score))

    if not rows:
        return df.head(0).copy()

    score_df = pd.DataFrame(rows, columns=["_idx", "_score"]).sort_values("_score", ascending=False)
    result = df.loc[score_df["_idx"].head(limit)].copy()
    result["_score"] = score_df["_score"].head(limit).values
    result["_issued_at"] = pd.to_datetime(result["date_issued"], errors="coerce")
    return result.sort_values(["_score", "_issued_at"], ascending=[False, False])


def _render_search_result(row: pd.Series) -> None:
    case_number = str(row.get("case_number", "")).strip()
    case_href = f"case-explorer?case={quote(case_number)}" if case_number else "case-explorer"
    case_name = escape(str(row.get("case_name", "Unknown case")))
    citation = _case_citation_display(row)
    citation_text = "" if citation == "—" else f" · {escape(citation)}"
    outcome = row.get("outcome")
    outcome_label = OUTCOME_LABELS.get(outcome, str(outcome).replace("_", " ").title()) if pd.notna(outcome) else "—"
    summary = row.get("summary_paragraph", "")
    clean_summary = _clean_summary_text(summary) if pd.notna(summary) and str(summary).strip() else ""
    summary_preview = escape(clean_summary[:260] + ("..." if len(clean_summary) > 260 else ""))

    st.markdown(
        f"""
        <div class="gsa-search-result">
            <a href="{case_href}" target="_self">{case_name}</a>
            <div class="gsa-meta">{_format_date(row.get("date_issued"))}{citation_text} · {escape(outcome_label)}</div>
            <p>{summary_preview or "No summary available."}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Chat helper functions ──────────────────────────────────────────────────────


def _hybrid_retrieval_available() -> bool:
    """Check if hybrid retrieval artifacts are available."""
    try:
        return (ROOT / "data" / "retrieval" / "case_documents.parquet").exists()
    except Exception:
        return False


def _retrieve_via_hybrid(
    query: str,
    previous_cases: List[str],
    num_cases: int,
) -> tuple[List[Dict], Dict]:
    """Call hybrid retrieval service and return legacy-shaped case dicts + diagnostics."""
    try:
        from utils.retrieval import build_context as _build_context, evidence_to_legacy
        from utils.retrieval.service import _try_load_service
    except Exception:
        return [], {}

    try:
        service = _try_load_service()
    except Exception:
        return [], {}
    if not service.is_ready():
        return [], {}

    try:
        response = service.retrieve(query, previous_cases=tuple(previous_cases or ()), limit=num_cases)
    except Exception:
        return [], {}

    cases = [evidence_to_legacy(case) for case in response.cases]
    diagnostics = {
        "plan": response.plan,
        "missing_fields": list(response.missing_fields),
        "sufficient": response.sufficient,
        "context": _build_context(response),
        "fused_trace": response.diagnostics.get("trace", {}),
        "latency": response.diagnostics.get("latency", {}),
    }
    return cases, diagnostics


def _try_hybrid_retrieval(query: str, num_cases: int, diagnostics: Dict) -> List[Dict]:
    """Try hybrid RetrievalService; populate diagnostics dict as side effect. Returns cases or []."""
    if not _hybrid_retrieval_available():
        return []
    cases, diag = _retrieve_via_hybrid(query, [], num_cases)
    if cases:
        diagnostics.update(diag)
    return cases


def _ask_generate_follow_ups(retrieved_cases: List[Dict]) -> List[str]:
    """Generate local follow-up questions from retrieved case names."""
    case_names = [c.get("name", "") for c in retrieved_cases if c.get("name") and c.get("name") != "Error"]
    if not case_names:
        return []
    primary = case_names[0]
    second = case_names[1] if len(case_names) > 1 else None
    questions = [f"What were the key facts in {primary}?"]
    if second:
        questions.extend([
            f"Compare the reasoning in {primary} and {second}.",
            f"How do the holdings in {primary} and {second} differ?",
        ])
    else:
        questions.extend([
            f"What rule did {primary} establish?",
            f"What did the dissent say in {primary}?",
        ])
    return questions


def _render_description_search(df: pd.DataFrame) -> None:
    """Render the Ask & Browse widget with AI-powered search."""
    with st.container(border=True):
        st.markdown("#### 💬 Ask & Browse")
        st.caption(
            "Describe a legal situation or ask a question — AI-powered search "
            "across NH Supreme Court opinions."
        )

        # Handle follow-up question flow
        _pending_followup = st.session_state.pop("_pending_followup_query", None)
        if _pending_followup:
            st.session_state["ask_query"] = _pending_followup
            st.session_state["_auto_ask"] = True

        ask_query = st.text_area(
            "Ask a question or describe a legal situation",
            label_visibility="collapsed",
            placeholder=(
                "e.g. police searched a suspect's cell phone without a warrant\n"
                "e.g. What are the landmark cases on free speech in schools?\n"
                "e.g. Compare specific NH Supreme Court decisions"
            ),
            height=120,
            key="ask_query",
        )

        col_slider, col_search, col_ask = st.columns([2, 1, 1])
        n_results = col_slider.slider("Results", 3, 20, 8, key="ask_n")
        search_clicked = col_search.button("🔍 Search", key="ask_search_btn", use_container_width=True)
        ask_clicked = col_ask.button("🚀 Ask AI", type="primary", key="ask_ask_btn", use_container_width=True)

        _auto_ask = st.session_state.pop("_auto_ask", False)
        if (search_clicked or ask_clicked or _auto_ask) and ask_query and len(ask_query.strip()) >= 3:
            query_text = ask_query.strip()

            referential = is_referential_followup(query_text)
            retrieval_query = build_retrieval_query(
                query_text,
                st.session_state.get("ask_previous_query", ""),
                st.session_state.get("ask_previous_cases", []),
            )

            with st.spinner("🔍 Searching cases..."):
                if search_clicked:
                    # Simple search - no LLM
                    fresh_cases = retrieve_cases(
                        retrieval_query,
                        source="nh-supreme-court",
                        top_k=n_results,
                    )
                    hybrid_diagnostics = {}
                else:
                    # Try hybrid retrieval for Ask AI
                    hybrid_diagnostics = {}
                    fresh_cases = _try_hybrid_retrieval(query_text, n_results, hybrid_diagnostics)
                    if not fresh_cases:
                        fresh_cases = retrieve_cases(
                            retrieval_query,
                            source="nh-supreme-court",
                            top_k=n_results,
                        )

                retrieved = merge_retrieved_cases(
                    fresh_cases,
                    st.session_state.get("ask_previous_cases", []),
                    include_previous=referential,
                    max_cases=n_results * 2,
                )

            st.session_state["ask_results"] = retrieved
            st.session_state["ask_selected_case"] = None
            st.session_state["ask_previous_query"] = query_text
            st.session_state["ask_previous_cases"] = retrieved

            # Generate AI answer if Ask AI button was clicked
            if ask_clicked or _auto_ask:
                if hybrid_diagnostics and hybrid_diagnostics.get("context"):
                    case_context = hybrid_diagnostics["context"]
                else:
                    case_context = format_context(retrieved)

                try:
                    conversation_history = []
                    if st.session_state.get("ask_previous_answer"):
                        conversation_history.append({
                            "role": "assistant",
                            "content": st.session_state["ask_previous_answer"]
                        })

                    response_stream = generate_chat_response(
                        user_message=query_text,
                        case_context=case_context,
                        conversation_history=conversation_history,
                        stream=True,
                    )

                    placeholder = st.empty()
                    chunks = []
                    if isinstance(response_stream, str):
                        response_text = response_stream
                    else:
                        buf = []
                        for chunk in response_stream:
                            if chunk:
                                buf.append(chunk)
                                if len(buf) >= 8:
                                    chunks.extend(buf)
                                    buf = []
                                    placeholder.markdown("".join(chunks) + " ▌")
                        if buf:
                            chunks.extend(buf)
                        placeholder.markdown("".join(chunks))
                        response_text = "".join(chunks)

                    formatted = format_with_links(response_text, retrieved)
                    st.session_state["ask_answer"] = formatted
                    st.session_state["ask_previous_answer"] = formatted
                    st.session_state["ask_follow_ups"] = _ask_generate_follow_ups(retrieved)
                    st.rerun()
                except Exception as e:
                    st.error(f"⚠️ AI error: {e}")
                    st.session_state.pop("ask_answer", None)
                    st.session_state.pop("ask_follow_ups", None)
            else:
                # Clear answer when doing simple search
                st.session_state.pop("ask_answer", None)
                st.session_state.pop("ask_follow_ups", None)

        # ── AI Answer block ──────────────────────────────────────────────
        if st.session_state.get("ask_answer"):
            st.markdown("---")
            st.markdown("### 💬 AI Answer")
            st.markdown(st.session_state["ask_answer"])

            follow_ups = st.session_state.get("ask_follow_ups", [])
            if follow_ups:
                selected = render_follow_ups(follow_ups, key_suffix="ask_answer")
                if selected:
                    st.session_state["_pending_followup_query"] = selected
                    st.rerun()

            retrieved = st.session_state.get("ask_results", [])
            with st.expander(f"📚 Sources ({len(retrieved)} cases)", expanded=False):
                render_sources(retrieved, key_suffix="ask_answer")

            st.markdown("---")

        # ── Search results (always shown when ask_results exists) ─────────
        results = st.session_state.get("ask_results")
        if results is not None:
            if not results:
                st.warning("No matching cases found. Try rephrasing your question.")
            else:
                col_list, col_detail = st.columns([2, 3], gap="large")

                with col_list:
                    st.markdown(f"**{len(results)} result(s)** — click a case to read it")
                    for rank, res in enumerate(results, 1):
                        sel_case = st.session_state.get("ask_selected_case")
                        case_id = res.get("href", "") or res.get("docket_number", "") or res.get("case_number", "") or f"case_{rank}"
                        is_selected = sel_case == case_id

                        with st.container(border=True):
                            st.markdown(f"**{rank}. {res.get('name', 'Unknown case')}**")
                            term = res.get("term", "")
                            score = res.get("score", 0)
                            st.caption(f"{term} term · score {score:.3f}")

                            btn_label = "✅ Selected" if is_selected else "View →"
                            btn_type = "primary" if is_selected else "secondary"
                            col_btn1, col_btn2 = st.columns(2)

                            with col_btn1:
                                if st.button(btn_label, key=f"ask_view_{rank}", type=btn_type, use_container_width=True):
                                    st.session_state["ask_selected_case"] = case_id
                                    st.rerun()

                            with col_btn2:
                                case_num = res.get("docket_number", "") or res.get("case_number", "")
                                if case_num and st.button("Open Case →", key=f"ask_open_{rank}", use_container_width=True):
                                    st.session_state["_nav_case"] = case_num
                                    st.switch_page(CASE_EXPLORER_PAGE)

                with col_detail:
                    sel_case = st.session_state.get("ask_selected_case")
                    if not sel_case:
                        st.markdown(
                            "<div style='height:200px;display:flex;align-items:center;"
                            "justify-content:center;border:2px dashed #ccc;border-radius:8px;"
                            "color:#888;font-size:1.1em;'>← Select a case to read it</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        # Find the selected case in results, then look up full row
                        selected_case = next(
                            (r for r in results if (r.get("href") or r.get("case_number")) == sel_case),
                            None
                        )

                        if not selected_case:
                            st.warning("Could not load case details.")
                        else:
                            # Look up full row from dataframe for richer fields
                            _cn = selected_case.get("docket_number", "") or selected_case.get("href", "")
                            _full_row = df[df["case_number"].astype(str) == str(_cn)]
                            _row = _full_row.iloc[0] if not _full_row.empty else None

                            st.subheader(selected_case.get("name", "Unknown Case"))
                            c1, c2 = st.columns([2, 1])
                            with c1:
                                if _row is not None:
                                    st.markdown(f"**Citation:** {_row.get('citation', '—')}")
                                    st.markdown(f"**Case Number:** {_row.get('case_number', '—')}")
                                    _pdf = _row.get("pdf_url", "")
                                    if _pdf and str(_pdf) not in ("", "nan"):
                                        st.markdown(f"[View Full Opinion PDF ↗]({_pdf})")
                                    date_argued = _row.get("date_argued")
                                    date_issued = _row.get("date_issued")
                                    if pd.notna(date_argued) and str(date_argued) != "nan":
                                        st.markdown(f"**Argued:** {str(date_argued)[:10]}")
                                    if pd.notna(date_issued) and str(date_issued) != "nan":
                                        st.markdown(f"**Decided:** {str(date_issued)[:10]}")
                                else:
                                    st.markdown(f"**Docket:** {selected_case.get('docket_number', '—')}")
                                    if selected_case.get("year"):
                                        st.markdown(f"**Year:** {selected_case['year']}")

                                outcome = selected_case.get("outcome", "")
                                if outcome and outcome not in ("", "Not available"):
                                    st.markdown(
                                        f'<span style="background:#003057;color:white;'
                                        f'padding:4px 12px;border-radius:4px;font-weight:bold;">'
                                        f'{outcome}</span>',
                                        unsafe_allow_html=True,
                                    )

                                if selected_case.get("snippet"):
                                    st.markdown(f"\n{selected_case['snippet']}")
                            with c2:
                                if _row is not None:
                                    st.markdown(f"**Author:** {_row.get('author_display', '—')}")
                                    st.markdown(f"**Vote:** {_row.get('vote_string', '—')}")
                                else:
                                    st.markdown(f"**Author:** {selected_case.get('author', '—')}")

                            st.divider()

                            if selected_case.get("facts_of_the_case"):
                                with st.expander("📋 Facts", expanded=True):
                                    st.write(selected_case["facts_of_the_case"])
                            if selected_case.get("conclusion"):
                                with st.expander("⚖️ Holding"):
                                    st.write(selected_case["conclusion"])


def _on_this_day(df: pd.DataFrame, today: date | None = None) -> tuple[pd.Series, pd.DataFrame, bool, str]:
    today = today or date.today()
    dated = df.assign(_issued_at=pd.to_datetime(df["date_issued"], errors="coerce"))
    dated = dated[dated["_issued_at"].notna()].copy()
    if dated.empty:
        return pd.Series(dtype=object), dated, False, f"{today.strftime('%B')} {today.day}"

    target_key = today.strftime("%m-%d")
    exact = dated[dated["_issued_at"].dt.strftime("%m-%d") == target_key].copy()
    if not exact.empty:
        exact = exact.sort_values("_issued_at", ascending=False)
        return exact.iloc[0], exact, True, f"{today.strftime('%B')} {today.day}"

    target_day = today.timetuple().tm_yday
    issued_day = dated["_issued_at"].dt.dayofyear
    day_delta = (issued_day - target_day).abs()
    dated["_calendar_delta"] = day_delta.map(lambda days: min(days, 366 - days))
    nearest = dated.sort_values(["_calendar_delta", "_issued_at"], ascending=[True, False])
    nearest_day = nearest.iloc[0]["_issued_at"].strftime("%m-%d")
    matches = nearest[nearest["_issued_at"].dt.strftime("%m-%d") == nearest_day].copy()
    label = _month_day_label(nearest.iloc[0]["_issued_at"])
    return matches.iloc[0], matches.sort_values("_issued_at", ascending=False), False, label


def _render_on_this_day(df: pd.DataFrame) -> None:
    row, matches, is_exact, display_day = _on_this_day(df)
    if row.empty:
        return

    case_name = escape(str(row.get("case_name", "Unknown case")))
    citation = _case_citation_display(row)
    citation_text = "" if citation == "—" else f" · {escape(citation)}"
    decided = _format_date(row.get("date_issued"))
    term = row.get("term_year", "")
    case_number = str(row.get("case_number", "")).strip()
    match_note = (
        f"{len(matches) - 1} more opinion{'s' if len(matches) != 2 else ''} from this date"
        if len(matches) > 1
        else "One opinion from this date"
    )
    eyebrow = "On this date" if is_exact else "Nearest court date"
    case_href = f"case-explorer?case={quote(case_number)}" if case_number else "case-explorer"
    graphic_path = ROOT / "data_files" / "onthisday.png"
    graphic_html = (
        f'<img src="data:image/png;base64,{base64.b64encode(graphic_path.read_bytes()).decode("ascii")}" alt="On this day">'
        if graphic_path.exists()
        else ""
    )

    st.markdown(
        f"""
        <div class="gsa-card gsa-on-this-day">
            <div>{graphic_html}</div>
            <div>
                <div class="gsa-stat-label">{eyebrow}</div>
                <h3>On This Day in NH Supreme Court History</h3>
                <p><strong>{display_day}</strong> · <a href="{case_href}" target="_self">{case_name}</a> was decided ({term}){citation_text}</p>
                <p style="margin-bottom:0;">Decided {decided} · {match_note}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if len(matches) > 1:
        with st.expander(f"View all {len(matches)} opinions from {display_day}"):
            for _, match_row in matches.iterrows():
                match_cn = str(match_row.get("case_number", "")).strip()
                match_name = escape(str(match_row.get("case_name", "Unknown case")))
                match_term = match_row.get("term_year", "")
                match_citation = _case_citation_display(match_row)
                match_citation_text = "" if match_citation == "—" else f" \u00b7 {escape(match_citation)}"
                match_href = f"case-explorer?case={quote(match_cn)}" if match_cn else "case-explorer"
                st.markdown(
                    f"- [{match_name}]({match_href}) ({match_term}){match_citation_text}",
                    unsafe_allow_html=True,
                )

def _render_stat(label: str, value: str) -> None:
    st.markdown(
        f"""
        <div class="gsa-stat">
            <div class="gsa-stat-label">{label}</div>
            <div class="gsa-stat-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard() -> None:
    """Landing dashboard that orients users before they enter an individual case."""
    _style_dashboard()
    _render_brand_header("NH Supreme Court analytics, opinions, case orders, and court trends")

    st.divider()

    df = load_opinions()
    if df.empty:
        st.warning(
            "No data loaded yet. Run the data pipeline first:\n\n"
            "```\npython scripts/update.py\n```"
        )
        st.stop()

    _render_on_this_day(df)

    st.subheader("Top Issues")
    all_topics: list[str] = []
    for topics in df["topics"].dropna():
        all_topics.extend(_as_list(topics))
    topic_counts = pd.Series(all_topics).value_counts().head(10)
    if topic_counts.empty:
        st.info("Topic tags are not available yet.")
    else:
        chips = " ".join(
            f'<a class="gsa-chip" href="topics?topic={quote(topic)}" target="_self">'
            f'{topic.replace("_", " ").title()} · {count}</a>'
            for topic, count in topic_counts.items()
        )
        st.markdown(chips, unsafe_allow_html=True)
    st.divider()

    _render_description_search(df)
    st.divider()

    current_year = int(df["term_year"].dropna().max())
    current_df = df[df["term_year"] == current_year].copy()
    unanimous_rate = int(round(df["is_unanimous"].fillna(False).mean() * 100))
    divided_count = int(df["has_dissent"].fillna(False).sum())

    st.subheader("Court Snapshot")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        _render_stat("Opinions", f"{len(df):,}")
    with s2:
        _render_stat("Current Term", str(current_year))
    with s3:
        _render_stat("Term Opinions", f"{len(current_df):,}")
    with s4:
        _render_stat("Unanimous Rate", f"{unanimous_rate}%")

    st.caption(f"Last updated: {data_last_updated()} · {divided_count:,} opinions include a dissent")

    add_gavel_glimpse_footer()


def render_case_explorer() -> None:
    """Single-opinion detail page."""
    _render_brand_header()

    st.divider()

    df = load_opinions()
    opinions_json = load_opinions_json()

    json_map: dict = {r["case_number"]: r for r in opinions_json}

    with st.sidebar:
        st.header("Case Explorer")

        if df.empty:
            st.warning(
                "No data loaded yet. Run the data pipeline first:\n\n"
                "```\npython scripts/update.py\n```"
            )
            st.stop()

        requested_case = st.session_state.pop("_nav_case", "") or st.query_params.get("case", "")
        requested_row = df[df["case_number"].astype(str) == str(requested_case)].head(1)

        available_years = sorted(df["term_year"].dropna().unique().astype(int), reverse=True)
        selected_year_index = 0
        if not requested_row.empty and pd.notna(requested_row.iloc[0].get("term_year")):
            requested_year = int(requested_row.iloc[0]["term_year"])
            if requested_year in available_years:
                selected_year_index = available_years.index(requested_year)
        selected_year = st.selectbox("Term Year", available_years, index=selected_year_index)

        year_df = df[df["term_year"] == selected_year].copy()
        case_options = year_df.sort_values("case_name")["case_name"].tolist()

        if not case_options:
            st.info(f"No cases found for {selected_year}")
            st.stop()

        labels = [
            f"{row['case_name']} ({row['case_number']})"
            for _, row in year_df.sort_values("case_name").iterrows()
        ]
        selected_label_index = 0
        if not requested_row.empty:
            requested_cn = str(requested_row.iloc[0]["case_number"])
            for idx, label in enumerate(labels):
                if label.endswith(f"({requested_cn})"):
                    selected_label_index = idx
                    break

        selected_label = st.selectbox("Select Case", labels, index=selected_label_index)
        selected_cn = labels.index(selected_label)
        case_row = year_df.sort_values("case_name").iloc[selected_cn]

        st.divider()
        st.caption(f"Last updated: {data_last_updated()}")
        st.caption(f"{len(df)} opinions in dataset")

    cn = case_row["case_number"]
    full_rec = json_map.get(cn, {})
    _full_text = load_opinion_text(cn)
    oral_argument = load_oral_argument(cn)

    col1, col2 = st.columns([3, 2])

    with col1:
        citation = _case_citation_display(case_row, full_rec)
        pdf_url = _display_or_dash(case_row.get("pdf_url"))
        st.subheader(str(case_row.get("case_name", "Unknown Case")))
        if pdf_url != "—":
            st.markdown(f"**Citation:** {citation} \u00a0 [View PDF ↗]({pdf_url})")
        else:
            st.markdown(f"**Citation:** {citation}")

        date_argued = case_row.get("date_argued")
        date_issued = case_row.get("date_issued")
        days = case_row.get("days_to_decision")
        dates_str = []
        if pd.notna(date_argued) and str(date_argued) != "nan":
            dates_str.append(f"Argued: {str(date_argued)[:10]}")
        if pd.notna(date_issued) and str(date_issued) != "nan":
            dates_str.append(f"Decided: {str(date_issued)[:10]}")
        if days and pd.notna(days):
            dates_str.append(f"({int(days)} days)")
        st.markdown(" · ".join(dates_str) if dates_str else "")

        meta_parts = []
        lc = case_row.get("lower_court")
        if lc and str(lc) != "nan":
            meta_parts.append(f"**Lower Court:** {lc}")
        lc_judge = case_row.get("lower_court_judge")
        if lc_judge and str(lc_judge) != "nan":
            meta_parts.append(f"**Trial Court Judge:** {lc_judge}")
        appeal = case_row.get("appeal_type")
        if appeal and str(appeal) != "nan":
            meta_parts.append(f"**Appeal Type:** {appeal.replace('_', ' ').title()}")
        for p in meta_parts:
            st.markdown(p)

        outcome = case_row.get("outcome")
        if outcome and str(outcome) != "nan":
            color = OUTCOME_COLORS.get(outcome, "#607D8B")
            label = OUTCOME_LABELS.get(outcome, outcome.replace("_", " ").title())
            st.markdown(
                f'<span style="background-color:{color};color:white;padding:4px 12px;'
                f'border-radius:4px;font-weight:bold;">{label}</span>',
                unsafe_allow_html=True,
            )
            st.markdown("")

        topics_raw = case_row.get("topics", "[]")
        try:
            topics = ast.literal_eval(topics_raw) if isinstance(topics_raw, str) else topics_raw
        except Exception:
            topics = []
        if topics:
            tags_html = " ".join(
                f'<span style="background:#E3F2FD;color:#003057;padding:2px 8px;'
                f'border-radius:12px;font-size:0.85em;margin:2px;">{t.replace("_", " ").title()}</span>'
                for t in topics
            )
            st.markdown(tags_html, unsafe_allow_html=True)
            st.markdown("")

        if not _render_case_brief_counsel(cn):
            _render_appearance_block(_full_text)

        votes = normalize_votes_for_bench(
            full_rec.get("votes", {}),
            date_argued=case_row.get("date_argued") or full_rec.get("date_argued"),
            date_issued=case_row.get("date_issued") or full_rec.get("date_issued"),
        )
        if votes:
            st.markdown("**Bench Vote**")
            fig = bench_diagram(votes)
            st.plotly_chart(fig, width="stretch", key=f"bench_{cn}")

            legend_html = ""
            for vote_type, color in VOTE_COLORS.items():
                legend_html += (
                    f'<span style="background:{color};color:white;'
                    f'padding:2px 8px;border-radius:4px;font-size:0.78em;margin:2px;">'
                    f'{vote_type.replace("_", " ").title()}</span> '
                )
            st.markdown(legend_html, unsafe_allow_html=True)

    with col2:
        author_display = case_row.get("author_display", "")
        vote_str = case_row.get("vote_string", "")
        if author_display and str(author_display) != "nan":
            st.markdown("**Opinion Author**")
            st.markdown(
                f"<div style='font-size:2rem;font-weight:700;line-height:1.2;margin-bottom:0.6rem;'>{author_display}</div>",
                unsafe_allow_html=True,
            )
        if vote_str and str(vote_str) != "nan":
            st.markdown("**Vote**")
            st.markdown(
                f"<div style='font-size:2rem;font-weight:700;line-height:1.2;margin-bottom:0.8rem;'>{vote_str}</div>",
                unsafe_allow_html=True,
            )

        is_unanimous = case_row.get("is_unanimous")
        has_dissent = case_row.get("has_dissent")
        if is_unanimous:
            st.success("Unanimous decision")
        elif has_dissent:
            st.error("Divided decision (dissent)")

        rsa_raw = case_row.get("rsa_citations", "[]")
        try:
            rsas = ast.literal_eval(rsa_raw) if isinstance(rsa_raw, str) else rsa_raw
        except Exception:
            rsas = []
        if rsas:
            st.markdown("**Statutes at Issue**")
            for rsa in rsas[:8]:
                st.markdown(f"- {rsa}")

    if oral_argument:
        st.divider()
        with st.container(border=True):
            st.markdown("**Oral Argument Transcript**")
            st.caption(
                "Machine-generated beta transcript. Speaker labels are inferred and may be inaccurate."
            )
            transcript_href = f"/oral-arguments?argument={quote(str(oral_argument['case_number']))}"
            st.markdown(f"[Read the oral argument transcript]({transcript_href})")
            if oral_argument.get("vimeo_url"):
                st.markdown(f"[Watch the original argument on Vimeo]({oral_argument['vimeo_url']})")
            _render_case_attorneys(str(oral_argument["case_number"]))

    # Load citations data
    citations_data = None
    cited_by_data = None
    try:
        citations_file = ROOT / "data" / "processed" / "citations.json"
        cited_by_file = ROOT / "data" / "processed" / "cited_by.json"
        if citations_file.exists():
            with open(citations_file) as f:
                citations_data = json.load(f)
        if cited_by_file.exists():
            with open(cited_by_file) as f:
                cited_by_data = json.load(f)
    except Exception:
        pass

    # Display citations if available
    if citations_data or cited_by_data:
        st.divider()

        # Cases this opinion cites
        if citations_data and cn in citations_data:
            cites = citations_data[cn].get("cites", [])
            if cites:
                with st.expander(f"📑 Cases Cited ({len(cites)})", expanded=False):
                    for cited_case in cites[:20]:  # Limit to first 20
                        # Find case name if available
                        cited_row = df[df["case_number"] == cited_case]
                        if not cited_row.empty:
                            cited_name = cited_row.iloc[0].get("case_name", cited_case)
                            cited_citation = _case_citation_display(cited_row.iloc[0])
                            citation_text = f" · {cited_citation}" if cited_citation != "—" else ""
                            st.markdown(f"- [{cited_name}](case-explorer?case={quote(cited_case)}){citation_text}")
                        else:
                            st.markdown(f"- {cited_case}")

        # Cases that cite this opinion
        if cited_by_data and cn in cited_by_data:
            citing_cases = cited_by_data[cn]
            if citing_cases:
                with st.expander(f"🔗 Cited By ({len(citing_cases)} cases)", expanded=False):
                    for citing_case in citing_cases[:20]:  # Limit to first 20
                        # Find case name if available
                        citing_row = df[df["case_number"] == citing_case]
                        if not citing_row.empty:
                            citing_name = citing_row.iloc[0].get("case_name", citing_case)
                            citing_citation = _case_citation_display(citing_row.iloc[0])
                            citation_text = f" · {citing_citation}" if citing_citation != "—" else ""
                            st.markdown(f"- [{citing_name}](case-explorer?case={quote(citing_case)}){citation_text}")
                        else:
                            st.markdown(f"- {citing_case}")

    intro_text = _extract_intro_text(_full_text)
    if intro_text:
        st.divider()
        st.markdown("**Summary**")
        st.markdown(
            f'<div style="font-family:sans-serif;line-height:1.7;font-size:0.95em;">{intro_text}</div>',
            unsafe_allow_html=True,
        )
    elif case_row.get("summary_paragraph") and str(case_row.get("summary_paragraph")) != "nan":
        st.divider()
        st.markdown("**Summary**")
        st.markdown(_clean_summary_text(case_row["summary_paragraph"]))

    with st.expander("Read Full Opinion Text"):
        if _full_text:
            highlighted = re.sub(
                r"(RSA\s+[\d\-A-Z:]+)",
                r'<mark style="background:#FFF9C4;">\1</mark>',
                _full_text,
            )
            st.markdown(
                f'<div style="font-family:sans-serif;line-height:1.7;white-space:pre-wrap;'
                f'font-size:0.92em;">{highlighted}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("Full text not available for this opinion.")

    add_gavel_glimpse_footer()


HOME_PAGE = st.Page(render_dashboard, title="Dashboard", icon="🏔️", url_path="", default=True)
CASE_EXPLORER_PAGE = st.Page(render_case_explorer, title="Case Explorer", icon="⚖️", url_path="case-explorer")
OPINIONS_PAGE = st.Page("pages/01_Opinions.py", title="Opinions", icon="📜", url_path="opinions")
JUSTICES_PAGE = st.Page("pages/02_Justices.py", title="Justices", icon="👩‍⚖️", url_path="justices")
ANALYSIS_PAGE = st.Page("pages/03_Analysis.py", title="Analysis", icon="📊", url_path="analysis")
ORAL_ARGUMENTS_PAGE = st.Page(
    "pages/08_Oral_Arguments.py",
    title="Oral Arguments",
    icon="🎙️",
    url_path="oral-arguments",
)
TOPICS_PAGE = st.Page("pages/04_Topics.py", title="Topics", icon="📚", url_path="topics")
CASE_ORDERS_PAGE = st.Page("pages/05_Case_Orders.py", title="Case Orders/3JX", icon="📋", url_path="case-orders")
TRIAL_COURTS_PAGE = st.Page("pages/07_Trial_Courts.py", title="Trial Courts", icon="🏛️", url_path="trial-courts")
ABOUT_PAGE = st.Page("pages/06_About.py", title="About", icon="ℹ️", url_path="about")

# Detail pages (accessed via links, not shown in main navigation)
ATTORNEY_DETAIL_PAGE = st.Page("pages/09_Attorney_Detail.py", title="Attorney Profile", icon="⚖️", url_path="attorney-profile")
FIRM_DETAIL_PAGE = st.Page("pages/10_Firm_Detail.py", title="Firm Profile", icon="🏢", url_path="firm-profile")

navigation = st.navigation(
    {
        "Main": [
            HOME_PAGE,
            CASE_EXPLORER_PAGE,
            OPINIONS_PAGE,
            JUSTICES_PAGE,
            ANALYSIS_PAGE,
            ORAL_ARGUMENTS_PAGE,
            TOPICS_PAGE,
            CASE_ORDERS_PAGE,
            TRIAL_COURTS_PAGE,
            ABOUT_PAGE,
        ],
        "Profiles": [
            ATTORNEY_DETAIL_PAGE,
            FIRM_DETAIL_PAGE,
        ]
    },
    position="sidebar",
)

navigation.run()
