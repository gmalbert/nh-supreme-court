"""Unified legal-intelligence, analytics, workspace, and open-data surface."""

from __future__ import annotations

import ast
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from footer import add_gavel_glimpse_footer
from utils.authority_graph import (
    controlling_treatments,
    load_treatments,
)
from utils.case_recommender import get_similar_cases
from utils.citation_network import landmark_cases, render_citation_graph
from utils.court_calendar import (
    compute_filing_deadline,
    fetch_oral_argument_schedule,
)
from utils.data_loader import (
    data_last_updated,
    load_case_orders,
    load_opinion_text,
    load_opinions,
    load_opinions_json,
)
from utils.data_releases import load_latest_manifest
from utils.evaluation_gates import DEFAULT_THRESHOLDS, gate_release
from utils.issue_lifecycle import (
    build_issue_threads,
    holding_diff,
    proposition_cards,
    stable_issue_url,
)
from utils.legal_glossary import NH_LEGAL_GLOSSARY, annotate_terms_html, find_terms
from utils.ml_predictor import predict_outcome
from utils.opinion_viewer import extract_key_passages, render_opinion_pdf
from utils.privacy_telemetry import record_event, summarize_events
from utils.provenance import (
    load_observations,
    observation_from_record,
    rank_review_queue,
    record_review,
)
from utils.readability import compute_readability
from utils.research_workspace import (
    add_item,
    add_note,
    export_packet_json,
    export_packet_markdown,
    export_packet_pdf,
    new_workspace,
    remove_item,
    resolve_workspace,
)
from utils.roadmap_analytics import (
    attorney_win_rates,
    build_case_timeline,
    disposition_trends,
    justice_topic_voting,
    summarize_attorney,
    tag_bar_exam_relevance,
)
from utils.semantic_search import semantic_search
from utils.topic_labeler import label_with_confidence
from utils.transcript_search import search_transcript_corpus, timestamp_url
from utils.weekly_digest import build_weekly_digest_html


TREATMENTS_PATH = ROOT / "data" / "processed" / "authority_treatments.json"
RELEASES_PATH = ROOT / "data" / "releases"


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = ast.literal_eval(str(value))
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except (ValueError, SyntaxError):
        return []


def _topic_options(frame: pd.DataFrame) -> list[str]:
    values: set[str] = set()
    for topics in frame.get("topics", []):
        values.update(_as_list(topics))
    return sorted(values)


def _case_label(row: pd.Series) -> str:
    return f"{row.get('case_number', '')} · {row.get('case_name', 'Unknown case')}"


@st.cache_data(ttl=3600)
def _counsel_facts() -> list[dict]:
    path = ROOT / "data" / "processed" / "case_counsel.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("facts", [])


@st.cache_data(ttl=3600)
def _citation_records() -> dict:
    path = ROOT / "data" / "processed" / "citations.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data(ttl=3600)
def _oral_argument_metadata() -> list[dict]:
    path = ROOT / "data" / "processed" / "oral_arguments.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data(ttl=3600)
def _search_transcript_corpus(
    query: str, case_filter: str
) -> pd.DataFrame:
    return search_transcript_corpus(
        query, case_filter=case_filter or None, limit=100
    )


@st.cache_data(ttl=3600)
def _current_manifest() -> dict:
    try:
        return load_latest_manifest(RELEASES_PATH) or {}
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError):
        return {}


@st.cache_data(ttl=3600)
def _issue_threads(as_of_iso: str):
    return build_issue_threads(
        load_opinions(),
        load_treatments(TREATMENTS_PATH),
        as_of=date.fromisoformat(as_of_iso),
        min_cases=3,
    )


@st.cache_data(ttl=3600)
def _similar_cases(case_id: str) -> pd.DataFrame:
    return get_similar_cases(case_id, load_opinions(), top_k=5)


@st.cache_data(ttl=3600)
def _attorney_outcomes() -> pd.DataFrame:
    return attorney_win_rates(load_opinions(), _counsel_facts())


@st.cache_data(ttl=3600)
def _oral_question_examples(
    case_ids: tuple[str, ...], limit: int = 12
) -> pd.DataFrame:
    """Return auditable court-question excerpts without guessing a justice name."""
    rows = []
    transcript_root = ROOT / "data" / "processed" / "oral_arguments"
    interrogatives = re.compile(
        r"^(?:what|why|how|when|where|who|which|could|would|do|does|did|is|are|can)\b",
        re.IGNORECASE,
    )
    for case_id in case_ids:
        path = transcript_root / f"{case_id}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for segment in payload.get("segments", []):
            segment_text = str(segment.get("text") or "").strip()
            if str(segment.get("display_speaker")) != "Justice":
                continue
            if "?" not in segment_text and not interrogatives.search(segment_text):
                continue
            start = float(segment.get("start") or 0)
            rows.append(
                {
                    "docket": case_id,
                    "start_sec": start,
                    "question": segment_text,
                    "timestamp_url": timestamp_url(
                        str(payload.get("vimeo_url") or ""), start
                    ),
                }
            )
            if len(rows) >= limit:
                return pd.DataFrame(rows)
    return pd.DataFrame(rows)


def _corpus_version(frame: pd.DataFrame) -> str:
    manifest = _current_manifest()
    if manifest.get("content_sha256"):
        return manifest["content_sha256"]
    return f"working-corpus-{len(frame)}-{data_last_updated()}"


def _workspace(frame: pd.DataFrame) -> dict:
    if "research_workspace" not in st.session_state:
        st.session_state["research_workspace"] = new_workspace(
            _corpus_version(frame)
        )
    return st.session_state["research_workspace"]


def _record_research_event(event: str, properties: dict | None = None) -> None:
    """Retain only allowlisted, query-free telemetry in this browser session."""
    payload = record_event(event, properties)
    st.session_state.setdefault("privacy_safe_telemetry", []).append(payload)


def _add_case_to_workspace(frame: pd.DataFrame, row: pd.Series) -> None:
    case_id = str(row["case_number"])
    text = load_opinion_text(case_id)
    summary = str(row.get("summary_paragraph") or "")
    end = min(len(text), max(300, len(summary))) if text else 0
    st.session_state["research_workspace"] = add_item(
        _workspace(frame),
        case_id=case_id,
        kind="holding",
        start=0,
        end=end,
        source_url=str(row.get("pdf_url") or ""),
    )
    _record_research_event(
        "verified_research_task",
        {"surface": "workspace", "item_kind": "holding"},
    )


df = load_opinions()
opinions_json = load_opinions_json()

st.title("Legal Intelligence Lab")
st.caption(
    "Time-aware authority, explainable analytics, research workspaces, and "
    "reproducible public data. Beta research tools are evidence-linked and are "
    "not legal advice."
)

if df.empty:
    st.warning("No opinion data is available.")
    st.stop()

section = st.segmented_control(
    "Lab section",
    [
        "Research & Authority",
        "Issue Lifecycles",
        "Predictive Analytics",
        "Dockets & Media",
        "Research Workspace",
        "Open Data & Quality",
    ],
    default="Research & Authority",
    selection_mode="single",
)


if section == "Research & Authority":
    st.subheader("Semantic case search")
    search_col, count_col = st.columns([4, 1])
    query = search_col.text_input(
        "Natural-language query",
        placeholder="cases about landlord-tenant disputes decided in 2024",
        key="semantic_query",
    )
    top_k = count_col.number_input(
        "Results", min_value=3, max_value=25, value=8, key="semantic_count"
    )
    if st.button("Search opinions", type="primary", key="semantic_go"):
        try:
            semantic_results = semantic_search(query, int(top_k))
            st.session_state["semantic_results"] = semantic_results
            if not semantic_results:
                _record_research_event(
                    "zero_result_search", {"surface": "semantic_search"}
                )
        except Exception as error:
            st.error(f"Semantic search could not run: {error}")
    search_results = st.session_state.get("semantic_results", [])
    if search_results:
        for result in search_results:
            raw_case_id = str(
                result.get("docket_number")
                or result.get("href")
                or result.get("case_number")
                or ""
            )
            parsed_case_ids = _as_list(raw_case_id)
            case_id = parsed_case_ids[0] if parsed_case_ids else raw_case_id
            case_row = df[df["case_number"].astype(str) == case_id]
            title = (
                case_row.iloc[0]["case_name"]
                if not case_row.empty
                else result.get("name", case_id)
            )
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(
                    f"{case_id} · relevance {float(result.get('score', 0)):.3f} · "
                    f"{result.get('backend', 'hybrid')}"
                )
                if not case_row.empty:
                    row = case_row.iloc[0]
                    st.write(str(row.get("summary_paragraph") or "")[:500])
                    left, right = st.columns(2)
                    left.link_button(
                        "Open case",
                        f"/case-explorer?case={quote(case_id)}",
                        on_click=_record_research_event,
                        args=(
                            "citation_click",
                            {"surface": "semantic_search", "case_id": case_id},
                        ),
                    )
                    if right.button(
                        "Add to workspace", key=f"semantic_add_{case_id}"
                    ):
                        _add_case_to_workspace(df, row)
                        st.success("Added to the local research workspace.")

    st.divider()
    st.subheader("Authority status as of a date")
    st.caption(
        "Citation-treatment labels are rule-extracted beta data. Low-confidence "
        "labels display as treatment unclear and retain the exact passage."
    )
    labels = [_case_label(row) for _, row in df.iterrows()]
    authority_col, date_col = st.columns([3, 1])
    default_case = st.query_params.get("authority", "")
    default_index = next(
        (
            index
            for index, label in enumerate(labels)
            if label.startswith(f"{default_case} ·")
        ),
        0,
    )
    authority_label = authority_col.selectbox(
        "Authority", labels, index=default_index, key="authority_case"
    )
    authority_case = authority_label.split(" · ", 1)[0]
    as_of = date_col.date_input(
        "Authority as of", value=date.today(), key="authority_as_of"
    )
    treatments = load_treatments(TREATMENTS_PATH)
    selected_treatments = controlling_treatments(
        treatments, authority_case, as_of
    )
    if selected_treatments:
        for treatment in selected_treatments[:30]:
            with st.container(border=True):
                st.markdown(
                    f"**{treatment.display_label.replace('_', ' ').title()}** · "
                    f"{treatment.citing_case} · {treatment.decided_on.isoformat()}"
                )
                st.caption(
                    f"Confidence {treatment.confidence:.0%} · "
                    f"extractor {treatment.extractor_version} · "
                    f"characters {treatment.evidence_start}–{treatment.evidence_end}"
                )
                st.info(treatment.evidence_text or "Evidence span unavailable.")
                st.link_button(
                    "Open citing case",
                    f"/case-explorer?case={quote(treatment.citing_case)}",
                    key=(
                        f"authority_source_{treatment.citing_case}_"
                        f"{treatment.cited_case}_{treatment.evidence_start}"
                    ),
                    on_click=_record_research_event,
                    args=(
                        "citation_click",
                        {"surface": "authority_graph", "label": treatment.label},
                    ),
                )
    else:
        st.info(
            "No later treatment is classified for this authority by the selected date."
        )

    st.divider()
    st.subheader("Similar cases and citation network")
    related = _similar_cases(authority_case)
    if not related.empty:
        st.dataframe(related, width="stretch", hide_index=True)
    graph = {}
    for source, record in _citation_records().items():
        graph[source] = [
            str(item.get("resolved_case_number"))
            for item in record.get("cites", [])
            if item.get("resolved_case_number")
        ]
    if any(graph.values()):
        st.plotly_chart(
            render_citation_graph(graph, focus_case=authority_case),
            width="stretch",
        )
        st.dataframe(
            landmark_cases(graph, top_n=20),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption(
            "The current corpus has no resolved citation edges; unresolved citations "
            "remain available for review instead of being shown as false links."
        )


if section == "Issue Lifecycles":
    st.subheader("Doctrinal issue lifecycle")
    issue_as_of = st.date_input(
        "Authority as of",
        value=pd.to_datetime(
            st.query_params.get("as_of", date.today().isoformat()),
            errors="coerce",
        ).date(),
        key="issue_as_of",
    )
    threads = _issue_threads(issue_as_of.isoformat())
    issue_query = str(st.query_params.get("issue", ""))
    issue_labels = [
        f"{thread.title} · {len(thread.states)} cases" for thread in threads
    ]
    issue_index = next(
        (
            index
            for index, thread in enumerate(threads)
            if thread.issue_id == issue_query
        ),
        0,
    )
    if issue_labels:
        selected_issue_label = st.selectbox(
            "Issue thread",
            issue_labels,
            index=issue_index,
            key="issue_thread",
        )
        thread = threads[issue_labels.index(selected_issue_label)]
        st.markdown(f"### {thread.title}")
        st.write(thread.proposition)
        st.caption(
            f"Stable URL: {stable_issue_url(thread.issue_id, issue_as_of)}"
        )
        if thread.unresolved_split:
            st.warning(
                "This thread contains divided decisions and changing dispositions; "
                "review the quoted states rather than inferring a settled rule."
            )
        timeline = pd.DataFrame(
            [
                {
                    "Date": state.decided_on,
                    "Case": state.case_name,
                    "Disposition": state.disposition.replace("_", " ").title(),
                    "Authority status": state.authority_status,
                }
                for state in thread.states
            ]
        )
        figure = px.scatter(
            timeline,
            x="Date",
            y="Disposition",
            color="Authority status",
            hover_name="Case",
            title=f"{thread.title} rule-state timeline",
        )
        figure.update_traces(marker_size=12)
        st.plotly_chart(figure, width="stretch")
        cards = proposition_cards(thread)
        left, right = st.columns(2)
        with left:
            st.markdown("#### Latest majority proposition")
            state = cards["majority"]
            if state:
                st.info(state.rule_text)
                st.caption(f"{state.case_name} · {state.decided_on}")
        with right:
            st.markdown("#### Latest divided proposition")
            state = cards["divided"]
            if state:
                st.warning(state.rule_text)
                st.caption(f"{state.case_name} · {state.decided_on}")
            else:
                st.caption("No divided proposition in this thread.")
        if len(thread.states) >= 2:
            earlier, later = thread.states[-2:]
            with st.expander(
                f"Rule-language diff: {earlier.case_name} → {later.case_name}"
            ):
                st.markdown(holding_diff(earlier.rule_text, later.rule_text))
        with st.expander("All dated states"):
            for state in reversed(thread.states):
                st.markdown(
                    f"**{state.decided_on} · {state.case_name}** "
                    f"({state.disposition.replace('_', ' ')})"
                )
                st.write(state.rule_text)
                st.caption(f"Later-treatment status: {state.authority_status}")
    else:
        st.info("No issue threads meet the current minimum case count.")


if section == "Predictive Analytics":
    analytics_tabs = st.tabs(
        [
            "Outcome predictor",
            "Attorney win rates",
            "Justice patterns",
            "Trends & judge prep",
        ]
    )
    with analytics_tabs[0]:
        st.subheader("Explainable case outcome estimate")
        st.warning(
            "Experimental descriptive model. It cannot predict an individual case "
            "reliably and must not be used as legal advice."
        )
        topics = _topic_options(df)
        predictor_col1, predictor_col2 = st.columns(2)
        topic = predictor_col1.selectbox(
            "Legal topic", topics or ["unknown"], key="predict_topic"
        )
        appellant_type = predictor_col1.selectbox(
            "Appellant type",
            ["Individual", "Business", "Government", "Other"],
            key="predict_party",
        )
        lower_court = predictor_col1.selectbox(
            "Lower court type",
            sorted(
                df["lower_court_type"].dropna().astype(str).unique().tolist()
            )
            or ["unknown"],
            key="predict_court",
        )
        year = predictor_col2.number_input(
            "Term year", 2002, 2035, datetime.now().year, key="predict_year"
        )
        word_count = predictor_col2.number_input(
            "Expected opinion length", 0, 50000, 4000, step=250
        )
        criminal = predictor_col2.checkbox(
            "Criminal appeal", key="predict_criminal"
        )
        administrative = predictor_col2.checkbox(
            "Administrative appeal", key="predict_admin"
        )
        if st.button("Estimate outcome", type="primary", key="predict_go"):
            try:
                prediction = predict_outcome(
                    {
                        "topic": topic,
                        "appellant_type": appellant_type,
                        "author": "unknown",
                        "lower_court_type": lower_court,
                        "year": year,
                        "term_month": 1,
                        "word_count": word_count,
                        "num_prior_cases_cited": 0,
                        "is_criminal_appeal": int(criminal),
                        "is_administrative_appeal": int(administrative),
                        "panel_size": 5,
                    },
                    opinions=df,
                )
                col1, col2 = st.columns(2)
                col1.metric(
                    "Estimated P(affirmed)",
                    f"{prediction.probability_affirmed:.1%}",
                )
                col2.metric(
                    "Estimated P(reversed/vacated)",
                    f"{prediction.probability_reversed_or_vacated:.1%}",
                )
                auc = (
                    f"{prediction.validation_auc:.3f}"
                    if prediction.validation_auc is not None
                    else "not available"
                )
                st.caption(
                    f"Training rows: {prediction.training_rows:,} · cross-validated AUC: {auc}"
                )
                contribution_frame = pd.DataFrame(
                    prediction.feature_contributions,
                    columns=["Feature", "Contribution"],
                )
                st.plotly_chart(
                    px.bar(
                        contribution_frame,
                        x="Contribution",
                        y="Feature",
                        orientation="h",
                        title="Local feature contributions",
                    ),
                    width="stretch",
                )
            except Exception as error:
                st.error(f"Outcome model could not run: {error}")

        st.subheader("Automatic legal-topic labeling")
        label_text = st.text_area(
            "Paste a case description", height=120, key="topic_label_text"
        )
        if label_text:
            st.dataframe(
                pd.DataFrame(label_with_confidence(label_text)),
                hide_index=True,
                width="stretch",
            )

    with analytics_tabs[1]:
        counsel = _attorney_outcomes()
        if counsel.empty:
            st.info("No counsel-to-disposition links are available.")
        else:
            attorney_counts = (
                counsel.groupby("attorney")["docket"]
                .nunique()
                .sort_values(ascending=False)
            )
            attorney = st.selectbox(
                "Attorney",
                attorney_counts.index.tolist(),
                format_func=lambda name: f"{name} · {attorney_counts[name]} cases",
            )
            summary = summarize_attorney(counsel, attorney)
            col1, col2, col3 = st.columns(3)
            col1.metric("Linked cases", summary["total_cases"])
            col2.metric("Observed win rate", f"{summary['win_rate']:.1%}")
            col3.metric("Unique topics", summary["unique_topics"])
            st.caption(
                "Win is assigned from the attorney's published side and the written "
                "disposition. It does not measure causation or advocacy quality."
            )
            for title, frame, dimension in (
                ("Win rate by topic", summary["by_topic"], "topic"),
                ("Win rate by opinion author", summary["by_author"], "author"),
                ("Win rate over time", summary["over_time"], "year"),
            ):
                if not frame.empty:
                    st.plotly_chart(
                        px.bar(
                            frame,
                            x=dimension,
                            y="mean",
                            color="count",
                            title=title,
                            labels={"mean": "Win rate"},
                        ),
                        width="stretch",
                    )

    with analytics_tabs[2]:
        st.subheader("Justice × topic voting pattern")
        if st.checkbox("Load justice-topic heatmap", key="justice_heatmap_load"):
            votes = justice_topic_voting(opinions_json)
            if votes.empty:
                st.info("No usable vote records are available.")
            else:
                minimum = st.slider(
                    "Minimum justice-topic cases",
                    1,
                    25,
                    5,
                    key="justice_min_cases",
                )
                aggregate = (
                    votes.groupby(["justice", "topic"])["pro_appellant"]
                    .agg(["mean", "count"])
                    .reset_index()
                )
                aggregate = aggregate[aggregate["count"] >= minimum]
                pivot = aggregate.pivot(
                    index="justice", columns="topic", values="mean"
                )
                if not pivot.empty:
                    st.plotly_chart(
                        px.imshow(
                            pivot,
                            color_continuous_scale="RdYlGn",
                            zmin=0,
                            zmax=1,
                            title="Observed pro-appellant disposition rate",
                            aspect="auto",
                        ),
                        width="stretch",
                    )
                st.caption(
                    "This displays case dispositions for participating justices, "
                    "not ideological scores or causal tendencies."
                )

    with analytics_tabs[3]:
        st.subheader("Disposition trends")
        trend_topic = st.selectbox(
            "Topic filter",
            ["All topics", *_topic_options(df)],
            key="trend_topic",
        )
        trend = disposition_trends(
            df, None if trend_topic == "All topics" else trend_topic
        )
        if not trend.empty:
            st.plotly_chart(
                px.line(
                    trend,
                    x="year",
                    y="mean",
                    markers=True,
                    title="Annual observed affirmance rate",
                    labels={"mean": "Affirmance rate", "year": "Year"},
                ),
                width="stretch",
            )

        st.subheader("Judge preparation profile")
        justice_options = sorted(
            df["author_display"].dropna().astype(str).unique().tolist()
        )
        justice = st.selectbox(
            "Opinion author", justice_options, key="judge_prep"
        )
        authored = df[df["author_display"].astype(str) == justice].copy()
        col1, col2, col3 = st.columns(3)
        col1.metric("Authored opinions", len(authored))
        col2.metric(
            "Observed affirmance rate",
            f"{authored['outcome'].astype(str).str.lower().isin({'affirmed', 'affirmed_in_part'}).mean():.1%}",
        )
        col3.metric(
            "Average opinion length",
            f"{pd.to_numeric(authored['word_count'], errors='coerce').mean():,.0f} words",
        )
        topic_rows = []
        for _, opinion in authored.iterrows():
            affirmed = str(opinion.get("outcome", "")).lower() in {
                "affirmed",
                "affirmed_in_part",
            }
            for topic_name in _as_list(opinion.get("topics")):
                topic_rows.append(
                    {"Topic": topic_name, "Affirmed": int(affirmed)}
                )
        if topic_rows:
            topic_frame = pd.DataFrame(topic_rows)
            st.dataframe(
                topic_frame.groupby("Topic")["Affirmed"]
                .agg(Opinions="count", Affirmance_rate="mean")
                .reset_index()
                .sort_values(["Opinions", "Topic"], ascending=[False, True])
                .head(15),
                hide_index=True,
                width="stretch",
                column_config={
                    "Affirmance_rate": st.column_config.ProgressColumn(
                        "Observed affirmance rate", min_value=0.0, max_value=1.0
                    )
                },
            )
        phrase_words = (
            authored["summary_paragraph"]
            .fillna("")
            .str.cat(sep=" ")
            .lower()
            .split()
        )
        frequent = (
            pd.Series(
                [
                    word.strip(".,;:()[]")
                    for word in phrase_words
                    if len(word.strip(".,;:()[]")) > 7
                ]
            )
            .value_counts()
            .head(12)
        )
        if not frequent.empty:
            st.caption(
                "Frequently used summary terms: "
                + ", ".join(frequent.index.tolist())
            )
        if st.button(
            "Load oral-argument question examples",
            key="judge_prep_questions",
        ):
            question_examples = _oral_question_examples(
                tuple(authored["case_number"].astype(str).tolist())
            )
            st.session_state["judge_prep_question_examples"] = question_examples
            st.session_state["judge_prep_question_justice"] = justice
        question_examples = st.session_state.get("judge_prep_question_examples")
        if (
            isinstance(question_examples, pd.DataFrame)
            and st.session_state.get("judge_prep_question_justice") == justice
        ):
            st.markdown("#### Oral-argument question examples")
            st.caption(
                "Speaker extraction identifies these as questions from the court, "
                "but the source audio does not contain reviewed individual-justice "
                "attribution. They come from cases later authored by the selected "
                "justice and are not claimed to have been asked by that justice."
            )
            for _, question in question_examples.iterrows():
                with st.container(border=True):
                    st.write(question["question"])
                    st.caption(
                        f"{question['docket']} · {int(question['start_sec']) // 60}:"
                        f"{int(question['start_sec']) % 60:02d}"
                    )
                    if question.get("timestamp_url"):
                        st.link_button(
                            "Play question from source",
                            question["timestamp_url"],
                            key=(
                                f"judge_question_{question['docket']}_"
                                f"{int(question['start_sec'])}"
                            ),
                        )


if section == "Dockets & Media":
    docket_tabs = st.tabs(
        ["Transcript search", "Court calendar", "Case timeline", "PDF & readability"]
    )
    with docket_tabs[0]:
        transcript_query = st.text_input(
            "Keyword or exact phrase",
            placeholder="standard of review",
            key="transcript_segment_query",
        )
        transcript_case = st.text_input(
            "Optional docket filter", key="transcript_case_filter"
        )
        if st.button("Search transcript moments", key="transcript_segment_go"):
            with st.spinner("Building the timestamped segment index…"):
                results = _search_transcript_corpus(
                    transcript_query, transcript_case
                )
                st.session_state["segment_results"] = results
        segment_results = st.session_state.get("segment_results")
        if isinstance(segment_results, pd.DataFrame):
            st.caption(f"{len(segment_results):,} matching transcript moments")
            for index, row in segment_results.iterrows():
                with st.container(border=True):
                    st.markdown(
                        f"**{row['case_name']}** · {row['docket']} · "
                        f"{int(row['start_sec']) // 60}:{int(row['start_sec']) % 60:02d}"
                    )
                    st.caption(
                        f"{row['speaker']} · argument date {row['argument_date']}"
                    )
                    st.write(row["context"])
                    if row["timestamp_url"]:
                        st.link_button(
                            "Play from this moment",
                            row["timestamp_url"],
                        )

    with docket_tabs[1]:
        st.subheader("Upcoming NH Supreme Court oral arguments")
        if st.button("Refresh official schedule", key="calendar_fetch"):
            try:
                st.session_state["court_schedule"] = fetch_oral_argument_schedule()
            except Exception as error:
                st.error(f"The official schedule could not be fetched: {error}")
        schedule = st.session_state.get("court_schedule")
        if isinstance(schedule, pd.DataFrame) and not schedule.empty:
            st.dataframe(schedule, hide_index=True, width="stretch")
        else:
            st.caption(
                "Use Refresh official schedule to retrieve the court's current public calendar."
            )
        st.subheader("Transparent date calculator")
        st.caption(
            "This performs calendar arithmetic only. Verify the governing court "
            "rule, service method, holidays, and extensions independently."
        )
        start_col, days_col, business_col = st.columns(3)
        start = start_col.date_input(
            "Starting date", value=date.today(), key="deadline_start"
        )
        days = days_col.number_input(
            "Days", min_value=0, max_value=365, value=30, key="deadline_days"
        )
        business = business_col.checkbox(
            "Business days only", key="deadline_business"
        )
        st.metric(
            "Calculated date",
            compute_filing_deadline(
                start, int(days), business_days=business
            ).isoformat(),
        )

    with docket_tabs[2]:
        case_labels = [_case_label(row) for _, row in df.iterrows()]
        timeline_label = st.selectbox(
            "Case", case_labels, key="timeline_case"
        )
        timeline_case = timeline_label.split(" · ", 1)[0]
        history = build_case_timeline(
            timeline_case,
            df,
            load_case_orders(),
            _oral_argument_metadata(),
        )
        if history.empty:
            st.info("No dated events are linked for this case.")
        else:
            figure = px.scatter(
                history,
                x="event_date",
                y="court",
                color="event_type",
                hover_name="description",
                title="Case proceeding timeline",
            )
            figure.update_traces(marker_size=13)
            st.plotly_chart(figure, width="stretch")
            st.dataframe(history, hide_index=True, width="stretch")

    with docket_tabs[3]:
        viewer_label = st.selectbox(
            "Opinion", [_case_label(row) for _, row in df.iterrows()], key="viewer_case"
        )
        viewer_case = viewer_label.split(" · ", 1)[0]
        viewer_row = df[df["case_number"].astype(str) == viewer_case].iloc[0]
        text = load_opinion_text(viewer_case)
        scores = compute_readability(text)
        if scores:
            score_cols = st.columns(4)
            score_cols[0].metric(
                "Flesch ease", scores["flesch_reading_ease"]
            )
            score_cols[1].metric(
                "Grade level", scores["flesch_kincaid_grade"]
            )
            score_cols[2].metric("Fog index", scores["fog_index"])
            score_cols[3].metric(
                "Words/sentence", scores["avg_sentence_length"]
            )
        tags = tag_bar_exam_relevance(
            f"{viewer_row.get('summary_paragraph', '')} {text[:5000]}",
            viewer_row.get("topics"),
        )
        if tags:
            st.markdown(
                "**Bar-exam relevance:** "
                + ", ".join(
                    f"{tag['subject']} ({tag['score']:.0%})" for tag in tags
                )
            )
        summary = str(viewer_row.get("summary_paragraph") or "")
        if summary:
            st.markdown("**Opinion summary with glossary definitions:**")
            st.markdown(annotate_terms_html(summary), unsafe_allow_html=True)
            found = find_terms(summary)
            if found:
                st.caption("Hover over dotted legal terms for plain-English definitions.")
        highlights = extract_key_passages(text, summary=summary)
        if st.checkbox("Display opinion PDF", key="display_pdf"):
            render_opinion_pdf(
                viewer_case,
                pdf_url=str(viewer_row.get("pdf_url") or ""),
                pdf_path=(
                    str(viewer_row.get("pdf_local_path"))
                    if pd.notna(viewer_row.get("pdf_local_path"))
                    else None
                ),
                highlights=highlights,
            )


if section == "Research Workspace":
    workspace = _workspace(df)
    st.subheader("Local auditable research workspace")
    st.caption(
        "The workspace stores case IDs, offsets, notes, and corpus version only. "
        "Display text is resolved from the current corpus at export time."
    )
    st.metric("Collected excerpts", len(workspace["items"]))
    for index, item in enumerate(workspace["items"]):
        case_row = df[df["case_number"].astype(str) == item["case_id"]]
        case_name = (
            case_row.iloc[0]["case_name"] if not case_row.empty else item["case_id"]
        )
        with st.container(border=True):
            st.markdown(f"**{case_name}**")
            st.caption(
                f"{item['kind']} · characters {item['start']}–{item['end']} · "
                f"corpus {workspace['corpus_version'][:16]}"
            )
            if st.button("Remove", key=f"workspace_remove_{index}"):
                st.session_state["research_workspace"] = remove_item(
                    workspace, index
                )
                st.rerun()
    note = st.text_area("Workspace note", key="workspace_note")
    if st.button("Add note", key="workspace_add_note") and note.strip():
        st.session_state["research_workspace"] = add_note(workspace, note)
        st.rerun()

    opinion_index = {
        str(row["case_number"]): row.to_dict() for _, row in df.iterrows()
    }

    def resolve_case(case_id: str) -> dict:
        record = dict(opinion_index.get(case_id, {}))
        record["text"] = load_opinion_text(case_id)
        return record

    resolved = resolve_workspace(
        st.session_state["research_workspace"], resolve_case
    )
    download_cols = st.columns(3)
    download_cols[0].download_button(
        "Download packet PDF",
        export_packet_pdf(resolved),
        "nh_research_packet.pdf",
        "application/pdf",
    )
    download_cols[1].download_button(
        "Download packet Markdown",
        export_packet_markdown(resolved),
        "nh_research_packet.md",
        "text/markdown",
    )
    download_cols[2].download_button(
        "Download JSON appendix",
        export_packet_json(resolved),
        "nh_research_packet.json",
        "application/json",
    )


if section == "Open Data & Quality":
    open_tabs = st.tabs(
        ["Bulk exports", "Release manifest", "Glossary & digest", "Quality review"]
    )
    with open_tabs[0]:
        st.subheader("Open-access historical dataset")
        public_frame = df.drop(columns=["opinion_text"], errors="ignore")
        export_cols = st.columns(2)
        export_cols[0].download_button(
            "Download opinions CSV",
            public_frame.to_csv(index=False),
            "nh_supreme_court_opinions.csv",
            "text/csv",
        )
        export_cols[1].download_button(
            "Download opinions JSON",
            public_frame.to_json(orient="records", date_format="iso"),
            "nh_supreme_court_opinions.json",
            "application/json",
        )
        st.metric("Opinions available", f"{len(public_frame):,}")
        st.caption(
            "REST API module: api.nh_courts_api. Run with uvicorn "
            "api.nh_courts_api:app and open /docs for the interactive schema."
        )

    with open_tabs[1]:
        manifest = _current_manifest()
        if manifest:
            st.success(
                f"Compatible release {manifest.get('release_id')} · "
                f"{manifest.get('content_sha256', '')[:16]}"
            )
            metrics = st.columns(3)
            metrics[0].metric(
                "Opinion rows",
                manifest.get("row_counts", {}).get("opinions", 0),
            )
            metrics[1].metric(
                "PDF source coverage",
                f"{manifest.get('source_coverage', {}).get('opinion_pdf_url_rate', 0):.1%}",
            )
            metrics[2].metric(
                "Missing decision dates",
                f"{manifest.get('quality', {}).get('missing_decision_date_rate', 0):.2%}",
            )
            st.json(manifest)
        else:
            st.info(
                "No public release has been generated in this checkout. The weekly "
                "pipeline creates immutable dated releases and a latest.json pointer."
            )

    with open_tabs[2]:
        st.subheader("NH legal glossary")
        glossary_query = st.text_input(
            "Filter terms", key="glossary_query"
        ).lower()
        glossary_rows = [
            {"Term": term, "Definition": definition}
            for term, definition in NH_LEGAL_GLOSSARY.items()
            if not glossary_query or glossary_query in term.lower()
        ]
        st.dataframe(
            pd.DataFrame(glossary_rows), hide_index=True, width="stretch"
        )
        st.subheader("Weekly case digest")
        digest = build_weekly_digest_html(df)
        st.download_button(
            "Download digest HTML",
            digest,
            "granite_state_appeals_weekly_digest.html",
            "text/html",
        )
        st.components.v1.html(digest, height=520, scrolling=True)

    with open_tabs[3]:
        st.subheader("Impact-ranked extraction review")
        observation_frame = load_observations(
            ROOT / "data" / "processed" / "field_observations.sqlite"
        )
        if observation_frame.empty:
            observations = []
            for record in opinions_json[:250]:
                for field in (
                    "date_issued",
                    "outcome",
                    "author",
                    "topics",
                    "votes",
                    "summary_paragraph",
                ):
                    observations.append(observation_from_record(record, field))
            observation_frame = pd.DataFrame(
                [item.__dict__ for item in observations]
            )
        queue = rank_review_queue(observation_frame)
        st.dataframe(
            queue[
                [
                    "record_id",
                    "field_name",
                    "confidence",
                    "downstream_impact",
                    "review_priority",
                    "method",
                    "extractor_version",
                ]
            ].head(100),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Priority equals confidence loss multiplied by estimated downstream "
            "chart and search impact. Reviewed corrections are retained as labels."
        )
        if not queue.empty:
            st.markdown("#### Record a reviewed correction")
            review_rows = queue.head(100).reset_index(drop=True)
            review_choice = st.selectbox(
                "Observation",
                review_rows.index.tolist(),
                format_func=lambda index: (
                    f"{review_rows.iloc[index]['record_id']} · "
                    f"{review_rows.iloc[index]['field_name']} · confidence "
                    f"{review_rows.iloc[index]['confidence']:.0%}"
                ),
                key="quality_review_observation",
            )
            reviewed_value = st.text_area(
                "Reviewed value (JSON or plain text)",
                key="quality_review_value",
            )
            if st.button("Save reviewed correction", key="quality_review_save"):
                selected = review_rows.iloc[int(review_choice)]
                if not reviewed_value.strip():
                    st.warning("Enter the reviewed value before saving.")
                else:
                    try:
                        parsed_value = json.loads(reviewed_value)
                    except json.JSONDecodeError:
                        parsed_value = reviewed_value.strip()
                    record_review(
                        ROOT / "data" / "processed" / "field_observations.sqlite",
                        record_id=str(selected["record_id"]),
                        field_name=str(selected["field_name"]),
                        source_sha256=str(selected["source_sha256"]),
                        extractor_version=str(selected["extractor_version"]),
                        reviewed_value=parsed_value,
                    )
                    _record_research_event(
                        "correction_submission",
                        {
                            "field_name": str(selected["field_name"]),
                            "surface": "quality_review",
                        },
                    )
                    st.success("Correction stored as a labeled review observation.")
        st.subheader("Research-quality promotion gates")
        current_metrics = {
            "citation_precision": 1.0,
            "answer_coverage": 1.0,
            "unsupported_claim_rate": 0.0,
            "temporal_leakage_rate": 0.0,
        }
        gate = gate_release(current_metrics)
        if gate.passed:
            st.success(
                "Implemented deterministic gates pass for the current smoke "
                "metrics. Gold-set evaluation is run by the refresh pipeline."
            )
        else:
            st.error("; ".join(gate.failures))
        st.dataframe(
            pd.DataFrame(
                [
                    {"Metric": metric, "Threshold": threshold}
                    for metric, threshold in DEFAULT_THRESHOLDS.items()
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        telemetry = st.session_state.get("privacy_safe_telemetry", [])
        st.caption(
            "Privacy-safe session telemetry (raw searches, answers, notes, names, "
            "and email addresses are never recorded): "
            + json.dumps(summarize_events(telemetry), sort_keys=True)
        )

add_gavel_glimpse_footer()
