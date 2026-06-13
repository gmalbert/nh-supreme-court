"""
cases.py — Granite State Appeals app entrypoint with Streamlit navigation.
"""

from __future__ import annotations

import ast
import base64
import re
import sys
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from utils.constants import APP_NAME, APP_TAGLINE, OUTCOME_COLORS, OUTCOME_LABELS, VOTE_COLORS
from utils.data_loader import (
    data_last_updated,
    load_case_orders,
    load_opinion_text,
    load_opinions,
    load_opinions_json,
)
from utils.charts import bench_diagram
from footer import add_gavel_glimpse_footer

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
        }
        .gsa-card h3 {
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
    query = query.strip()
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
    citation = row.get("citation")
    citation_text = "" if pd.isna(citation) or not str(citation).strip() else f" · {escape(str(citation))}"
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


def _render_description_search(df: pd.DataFrame) -> None:
    with st.container(border=True):
        st.subheader("🔍 Find Cases by Description")
        st.caption("Describe a legal situation in plain language and find related NH Supreme Court opinions.")
        with st.form("description_search_form"):
            query = st.text_area(
                "Case description",
                placeholder=(
                    "e.g. police searched a suspect's cell phone without a warrant\n"
                    "e.g. an employee challenged termination after a personnel board ruling\n"
                    "e.g. parents disputed alimony, property division, or parenting time"
                ),
                label_visibility="collapsed",
                height=112,
            )
            c1, c2 = st.columns([1, 4])
            with c1:
                limit = st.slider("Results", min_value=3, max_value=20, value=8)
            with c2:
                submitted = st.form_submit_button("🔍 Find Cases")

        if submitted:
            results = _search_opinions(df, query, limit)
            if results.empty:
                st.info("No matching opinions found. Try adding issue words, a statute, or a party type.")
            else:
                st.markdown(f"**Top {len(results)} matches**")
                for _, row in results.iterrows():
                    _render_search_result(row)


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
    citation = row.get("citation")
    citation_text = "" if pd.isna(citation) or not str(citation).strip() else f" · {escape(str(citation))}"
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
    st.page_link("pages/01_Opinions.py", label="Explore Opinions")


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


def _render_nav_card(title: str, body: str, href: str, label: str, icon: str) -> None:
    st.markdown(
        f"""
        <div class="gsa-card gsa-nav-card">
            <div>
                <h3><span class="gsa-card-icon">{icon}</span>{title}</h3>
                <p>{body}</p>
            </div>
            <a class="gsa-card-button" href="{href}" target="_self">{label} →</a>
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
    orders_df = load_case_orders()

    if df.empty:
        st.warning(
            "No data loaded yet. Run the data pipeline first:\n\n"
            "```\npython scripts/update.py\n```"
        )
        st.stop()

    _render_on_this_day(df)
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

    st.divider()

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
    st.page_link("pages/04_Topics.py", label="Explore issue areas")

    st.divider()

    st.subheader("Explore the Court")
    r1c1, r1c2 = st.columns(2)
    with r1c1:
        _render_nav_card(
            "Opinions",
            "Search and filter published decisions by term, outcome, author, RSA citation, and case name.",
            "opinions",
            "Open Opinions",
            "⚖️",
        )
    with r1c2:
        _render_nav_card(
            "Justices",
            "Compare authorship, voting participation, unanimity, and dissent patterns across the bench.",
            "justices",
            "Open Justices",
            "👥",
        )

    r2c1, r2c2 = st.columns(2)
    with r2c1:
        _render_nav_card(
            "Analysis",
            "Review term-by-term trends, outcome mix, reversal rates, voting patterns, and decision timing.",
            "analysis",
            "Open Analysis",
            "📊",
        )
    with r2c2:
        order_count = len(orders_df) if not orders_df.empty else 0
        _render_nav_card(
            "Case Orders and 3JX",
            f"Browse {order_count:,} orders, sentence-review dispositions, and non-opinion court activity.",
            "case-orders",
            "Open Case Orders",
            "📋",
        )

    r3c1, r3c2 = st.columns(2)
    with r3c1:
        _render_nav_card(
            "Trial Courts",
            "See lower-court sources, trial judges, appeal pathways, and which cases return for remand.",
            "trial-courts",
            "Open Trial Courts",
            "🏛️",
        )
    with r3c2:
        _render_nav_card(
            "Case Explorer",
            "Use the focused single-opinion reader once you already know which case you want to inspect.",
            "case-explorer",
            "Open Case Explorer",
            "🔎",
        )

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

        requested_case = st.query_params.get("case", "")
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

    col1, col2 = st.columns([3, 2])

    with col1:
        citation = case_row.get("citation") or "—"
        pdf_url = case_row.get("pdf_url", "")
        st.subheader(str(case_row.get("case_name", "Unknown Case")))
        if pdf_url and str(pdf_url) not in ("", "nan"):
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

        votes = full_rec.get("votes", {})
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
TOPICS_PAGE = st.Page("pages/04_Topics.py", title="Topics", icon="📚", url_path="topics")
CASE_ORDERS_PAGE = st.Page("pages/05_Case_Orders.py", title="Case Orders/3JX", icon="📋", url_path="case-orders")
TRIAL_COURTS_PAGE = st.Page("pages/07_Trial_Courts.py", title="Trial Courts", icon="🏛️", url_path="trial-courts")
ABOUT_PAGE = st.Page("pages/06_About.py", title="About", icon="ℹ️", url_path="about")

navigation = st.navigation(
    [
        HOME_PAGE,
        CASE_EXPLORER_PAGE,
        OPINIONS_PAGE,
        JUSTICES_PAGE,
        ANALYSIS_PAGE,
        TOPICS_PAGE,
        CASE_ORDERS_PAGE,
        TRIAL_COURTS_PAGE,
        ABOUT_PAGE,
    ],
    position="sidebar",
)

navigation.run()

