"""Public, read-only API backed by the existing court data release."""

from __future__ import annotations

import json
import ast
from dataclasses import asdict
import re
from collections import Counter
from datetime import date, datetime
from functools import lru_cache
from threading import Lock
import logging
import os
import hmac
from contextlib import asynccontextmanager
from threading import Thread

import pandas as pd
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

# Shared helper modules should use framework-neutral caching and server
# environment secrets when they are loaded by this FastAPI application.
os.environ.setdefault("NHSC_APP_FRAMEWORK", "fastapi")

from utils.constants import JUSTICE_DISPLAY, JUSTICE_KEYS, OUTCOME_LABELS, OUTCOME_COLORS, VOTE_COLORS
from utils.runtime_paths import data_root

_retrieval_lock = Lock()
logger = logging.getLogger(__name__)
_search_status = "not_started"


@lru_cache(maxsize=1)
def _retriever():
    from utils.chat_retriever import CaseRetriever
    return CaseRetriever()


def _warm_search_index() -> None:
    """Build the same in-memory search index before the first visitor needs it."""
    global _search_status
    _search_status = "warming"
    try:
        with _retrieval_lock:
            retriever = _retriever()
            if retriever._nh_vectorizer is None:
                retriever._build_nh_index()
            if retriever._nh_vectorizer is None or retriever._nh_matrix is None:
                raise RuntimeError("Search index could not be built")
        _search_status = "ready"
        logger.info("Research search index is ready")
    except Exception:
        _search_status = "unavailable"
        logger.exception("Research search index prewarming failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _search_status
    configured = os.environ.get("NHSC_PREWARM_SEARCH", "").strip().lower()
    if configured in {"1", "true", "yes"} or (not configured and os.environ.get("NHSC_RUNTIME_MODE", "").strip().lower() in {"1", "true", "yes", "production"}):
        _search_status = "warming"
        Thread(target=_warm_search_index, name="nhsc-search-prewarm", daemon=True).start()
    else:
        _search_status = "not_started"
    yield


app = FastAPI(title="Granite State Appeals API", lifespan=lifespan)


@app.get("/api/site-status")
def site_status() -> dict:
    """Expose the same public data freshness summary shown in the Streamlit sidebar."""
    manifest_path = data_root() / "processed" / "refresh_manifest.json"
    manifest = {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if not isinstance(manifest, dict):
        manifest = {}
    timestamp = manifest.get("refresh_timestamp", "")
    updated = ""
    if timestamp:
        try:
            updated = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime("%B %d, %Y")
        except ValueError:
            updated = timestamp
    steps = manifest.get("steps", {})
    failed_steps = [name for name, status in steps.items() if status != "success"]
    if not updated:
        opinions_path = data_root() / "processed" / "opinions.csv"
        if opinions_path.is_file():
            updated = datetime.fromtimestamp(opinions_path.stat().st_mtime).strftime("%B %d, %Y")
    return {
        "updated": updated,
        "has_manifest": bool(manifest),
        "has_steps": bool(steps),
        "all_success": bool(steps) and not failed_steps,
        "failed_count": len(failed_steps),
        "has_data": (data_root() / "processed" / "opinions.csv").is_file(),
    }


@app.get("/api/research/status")
def research_status() -> dict:
    return {"status": _search_status}


@app.get("/api/dashboard")
def dashboard() -> dict:
    df = opinions()
    if df.empty:
        raise HTTPException(status_code=503, detail="Opinion data is unavailable")
    topics = Counter()
    for value in df["topics"].dropna():
        try:
            parsed = ast.literal_eval(value) if isinstance(value, str) else value
            if isinstance(parsed, list):
                topics.update(str(item) for item in parsed if str(item).strip())
        except (ValueError, SyntaxError):
            continue
    dated = df.assign(_issued_at=pd.to_datetime(df["date_issued"], errors="coerce"))
    dated = dated[dated["_issued_at"].notna()].copy()
    today = date.today()
    matches = dated[dated["_issued_at"].dt.strftime("%m-%d") == today.strftime("%m-%d")].copy()
    exact = not matches.empty
    if matches.empty and not dated.empty:
        delta = (dated["_issued_at"].dt.dayofyear - today.timetuple().tm_yday).abs()
        dated["_calendar_delta"] = delta.map(lambda days: min(days, 366 - days))
        nearest = dated.sort_values(["_calendar_delta", "_issued_at"], ascending=[True, False])
        matches = nearest[nearest["_issued_at"].dt.strftime("%m-%d") == nearest.iloc[0]["_issued_at"].strftime("%m-%d")].copy()
    matches = matches.sort_values("_issued_at", ascending=False)
    matches = matches.drop(columns=["_issued_at", "_calendar_delta"], errors="ignore")
    year = int(df["term_year"].dropna().max())
    return {
        "topics": [{"name": name, "count": count} for name, count in topics.most_common(10)],
        "history": records(matches), "history_exact": exact,
        "total": len(df), "current_year": year, "term_opinions": int(df["term_year"].eq(year).sum()),
        "unanimous_rate": round(float(df["is_unanimous"].fillna(False).mean()) * 100),
        "dissent_count": int(df["has_dissent"].fillna(False).sum()),
        "updated": opinion_filters()["updated"],
    }


class ResearchCase(BaseModel):
    name: str = Field(default="", max_length=500)
    source: str = Field(default="nh-supreme-court", max_length=50)
    term: str | None = Field(default=None, max_length=100)
    year: str | int | None = None
    docket_number: str | None = Field(default=None, max_length=100)
    case_number: str | None = Field(default=None, max_length=100)
    href: str | None = Field(default=None, max_length=1000)
    url: str | None = Field(default=None, max_length=1000)
    citation: str | None = Field(default=None, max_length=300)
    score: float | None = None
    outcome: str | None = Field(default=None, max_length=200)
    snippet: str | None = Field(default=None, max_length=4000)
    description: str | None = Field(default=None, max_length=6000)
    facts: str | None = Field(default=None, max_length=6000)
    question: str | None = Field(default=None, max_length=4000)
    holding: str | None = Field(default=None, max_length=6000)
    vote_split: str | None = Field(default=None, max_length=500)
    majority_justices: str | list[str] | None = None
    minority_justices: str | list[str] | None = None
    opinion_authors: str | list[str] | None = None
    majority_opinion_authors: str | list[str] | None = None
    dissent_authors: str | list[str] | None = None
    concurrence_authors: str | list[str] | None = None
    facts_of_the_case: str | None = Field(default=None, max_length=6000)
    conclusion: str | None = Field(default=None, max_length=6000)
    author: str | None = Field(default=None, max_length=300)


class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    limit: int = Field(default=8, ge=3, le=20)
    previous_query: str = Field(default="", max_length=4000)
    previous_answer: str = Field(default="", max_length=15000)
    previous_cases: list[ResearchCase] = Field(default_factory=list, max_length=40)


class LegalSearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    limit: int = Field(default=8, ge=3, le=25)


class WorkspaceItem(BaseModel):
    case_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=100)
    kind: str = Field(max_length=100)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    page_number: int | None = Field(default=None, ge=1)
    source_url: str = Field(default="", max_length=2000)


class WorkspaceNote(BaseModel):
    text: str = Field(max_length=10000)
    created_at: str = Field(max_length=100)
    case_id: str | None = Field(default=None, max_length=100)


class WorkspacePayload(BaseModel):
    schema_version: int = 1
    corpus_version: str = Field(min_length=1, max_length=300)
    items: list[WorkspaceItem] = Field(default_factory=list, max_length=100)
    notes: list[WorkspaceNote] = Field(default_factory=list, max_length=100)


@app.post("/api/research/search")
def research_search(request: ResearchRequest) -> dict:
    results, _ = _research_results(request)
    return {"results": results}


def _research_results(request: ResearchRequest, use_hybrid: bool = False) -> tuple[list[dict], str | None]:
    from utils.chat_retriever import build_retrieval_query, format_context, is_referential_followup, merge_retrieved_cases
    from utils.temporal_research import filter_as_of, parse_as_of_date

    global _search_status
    query = request.query.strip()
    previous_cases = [case.model_dump(exclude_none=True) for case in request.previous_cases]
    referential = is_referential_followup(query)
    retrieval_query = build_retrieval_query(query, request.previous_query, previous_cases)
    fresh_cases: list[dict] = []
    hybrid_context = None

    if use_hybrid and (data_root() / "retrieval" / "case_documents.parquet").is_file():
        try:
            from utils.retrieval import build_context, evidence_to_legacy
            from utils.retrieval.service import get_service_for_session

            service = get_service_for_session()
            if service.is_ready():
                previous_ids = tuple(
                    str(case.get("docket_number") or case.get("case_number") or "")
                    for case in previous_cases
                    if case.get("docket_number") or case.get("case_number")
                )
                response = service.retrieve(query, previous_cases=previous_ids, limit=request.limit)
                fresh_cases = [evidence_to_legacy(case) for case in response.cases]
                hybrid_context = build_context(response)
        except Exception:
            logger.exception("Hybrid retrieval failed; using standard search")

    if not fresh_cases:
        with _retrieval_lock:
            retriever = _retriever()
            fresh_cases = retriever.retrieve_cases(retrieval_query, source="nh-supreme-court", top_k=request.limit)
            _search_status = "ready" if retriever._nh_vectorizer is not None and retriever._nh_matrix is not None else "unavailable"

    results = merge_retrieved_cases(
        fresh_cases,
        previous_cases,
        include_previous=referential,
        max_cases=request.limit * 2,
    )
    as_of = parse_as_of_date(query)
    results = filter_as_of(results, as_of)
    if hybrid_context and referential and previous_cases:
        hybrid_context = f"{hybrid_context}\n\nPreviously retrieved cases for this follow-up:\n{format_context(previous_cases)}"
    return results, hybrid_context


@app.post("/api/research/answer")
def research_answer(request: ResearchRequest) -> dict:
    from utils.chat_retriever import format_context
    from utils.chat_formatter import format_with_links
    from utils.chat_provider import generate_chat_response
    from utils.claim_verifier import verify_answer, verified_claim_to_dict
    query = request.query.strip()
    found, hybrid_context = _research_results(request, use_hybrid=True)
    from utils.temporal_research import parse_as_of_date
    as_of = parse_as_of_date(query)
    if not found:
        return {"results": [], "answer": "", "verified_claims": [], "coverage": 0, "unsupported_removed": 0}
    try:
        case_context = hybrid_context or format_context(found)
        conversation_history = ([{"role": "assistant", "content": request.previous_answer}] if request.previous_answer else [])
        response = generate_chat_response(user_message=query, case_context=case_context, conversation_history=conversation_history, stream=False)
        answer = response if isinstance(response, str) else "".join(response)
    except Exception as exc:
        logger.exception("Research answer generation failed")
        raise HTTPException(status_code=503, detail="AI answer is unavailable. Please try search instead.") from exc
    verification = verify_answer(answer, found)
    return {
        "results": found, "answer": format_with_links(verification.publishable_text, found),
        "verified_claims": [verified_claim_to_dict(claim) for claim in verification.verified_claims],
        "coverage": verification.answer_coverage, "unsupported_removed": len(verification.unsupported_claims),
        "as_of": as_of.isoformat() if as_of else None,
    }


@lru_cache(maxsize=2)
def _read_opinions(path: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    return pd.read_csv(path, low_memory=False, encoding="utf-8")


def opinions() -> pd.DataFrame:
    path = data_root() / "processed" / "opinions.csv"
    if not path.is_file():
        raise HTTPException(status_code=503, detail="Opinion data is unavailable")
    return _read_opinions(str(path), path.stat().st_mtime_ns)


def records(frame: pd.DataFrame) -> list[dict]:
    # pandas handles NaN, numpy scalars and timestamps consistently in JSON.
    return json.loads(frame.to_json(orient="records", date_format="iso"))


@app.get("/api/health")
def health() -> dict:
    path = data_root() / "processed" / "opinions.csv"
    if not path.is_file():
        raise HTTPException(status_code=503, detail="Opinion data is unavailable")
    return {"status": "ok"}


@app.get("/api/opinions/filters")
def opinion_filters() -> dict:
    df = opinions()
    years = sorted(int(y) for y in df["term_year"].dropna().unique())
    outcomes = sorted(str(v) for v in df["outcome"].dropna().unique())
    authors = sorted(str(v) for v in df["author"].dropna().unique())
    return {
        "years": years,
        "outcomes": [{"value": v, "label": OUTCOME_LABELS.get(v, v.replace("_", " ").title()), "color": OUTCOME_COLORS.get(v, "#607D8B")} for v in outcomes],
        "authors": [{"value": v, "label": JUSTICE_DISPLAY.get(v, v)} for v in authors],
        "updated": datetime.fromtimestamp((data_root() / "processed" / "opinions.csv").stat().st_mtime).strftime("%B %d, %Y %I:%M %p"),
    }


@app.get("/api/compare-cases")
def compare_cases(first: str = Query(min_length=1, max_length=100), second: str = Query(min_length=1, max_length=100)) -> dict:
    from utils.similar_cases import explain_similarity
    left, right = get_opinion(first), get_opinion(second)
    def normalize(opinion):
        row = dict(opinion)
        for column in ("topics", "rsa_citations"):
            value = row.get(column)
            if isinstance(value, str):
                try:
                    value = ast.literal_eval(value)
                except (SyntaxError, ValueError):
                    value = []
            row[column] = value if isinstance(value, list) else []
        return row
    reasons = explain_similarity(normalize(left["opinion"]), normalize(right["opinion"])) if first != second else []
    # Missing metadata is not evidence that the cases share an outcome,
    # author, or originating court.
    for field, prefix in (("outcome", "Same outcome:"), ("author", "Same author:"), ("lower_court_type", "Both from ")):
        if not left["opinion"].get(field) or not right["opinion"].get(field):
            reasons = [reason for reason in reasons if not reason.startswith(prefix)]
    if first != second and not reasons:
        reasons = ["Similar legal issues"]
    return {"first": left, "second": right, "reasons": reasons}


@app.get("/api/compare-cases/options")
def compare_case_options() -> dict:
    # Comparison searches the full opinion dataset in source order, including
    # records without a term year (the case explorer's selector excludes them).
    df = opinions().dropna(subset=["case_number"])
    return {"items": records(df[["case_number", "case_name"]])}


@app.get("/api/opinions")
def list_opinions(
    year: list[int] = Query(default=[]),
    outcome: list[str] = Query(default=[]),
    author: list[str] = Query(default=[]),
    decision: str = Query(default="all", pattern="^(all|unanimous|dissent|concurrence)$"),
    q: str = Query(default="", max_length=300),
    table_q: str = Query(default="", max_length=300),
    sort_by: str = Query(default="date_issued", pattern="^(citation|case_name|date_issued|author_display|vote_string|outcome)$"),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    df = opinions()
    filtered = _filter_opinions(df, year, outcome, author, decision, q)
    filtered_count = len(filtered)
    if table_q.strip():
        table_query = table_q.strip()
        searchable = ["citation", "case_name", "date_issued", "author_display", "vote_string", "outcome", "pdf_url"]
        mask = pd.Series(False, index=filtered.index)
        for column in searchable:
            if column in filtered:
                mask |= filtered[column].fillna("").astype(str).str.contains(table_query, case=False, regex=False)
        filtered = filtered[mask]
    if sort_by == "date_issued":
        sort_values = pd.to_datetime(filtered[sort_by], errors="coerce")
    else:
        sort_values = filtered[sort_by].fillna("").astype(str).str.casefold()
    filtered = filtered.assign(_sort_value=sort_values).sort_values(
        "_sort_value", ascending=sort_direction == "asc", na_position="last", kind="stable"
    ).drop(columns="_sort_value")
    return {"total": len(df), "filtered_count": filtered_count, "count": len(filtered), "items": records(filtered.iloc[offset:offset + limit])}


def _filter_opinions(df: pd.DataFrame, year: list[int], outcome: list[str], author: list[str], decision: str, q: str) -> pd.DataFrame:
    filtered = df
    if year:
        filtered = filtered[filtered["term_year"].isin(year)]
    if outcome:
        filtered = filtered[filtered["outcome"].isin(outcome)]
    if author:
        filtered = filtered[filtered["author"].isin(author)]
    column = {"unanimous": "is_unanimous", "dissent": "has_dissent", "concurrence": "has_separate_concurrence"}.get(decision)
    if column:
        filtered = filtered[filtered[column].eq(True)]  # noqa: E712
    if q:
        mask = pd.Series(False, index=filtered.index)
        for col in ("case_name", "rsa_citations", "case_number"):
            mask |= filtered[col].fillna("").astype(str).str.contains(q, case=False, regex=False)
        filtered = filtered[mask]
    dates = pd.to_datetime(filtered["date_issued"], errors="coerce")
    filtered = filtered.assign(_date_sort=dates).sort_values("_date_sort", ascending=False, na_position="last").drop(columns="_date_sort")
    return filtered


@app.get("/api/opinions.csv")
def download_opinions(
    year: list[int] = Query(default=[]),
    outcome: list[str] = Query(default=[]),
    author: list[str] = Query(default=[]),
    decision: str = Query(default="all", pattern="^(all|unanimous|dissent|concurrence)$"),
    q: str = Query(default="", max_length=300),
) -> Response:
    filtered = _filter_opinions(opinions(), year, outcome, author, decision, q)
    return Response(filtered.to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="nh_sc_opinions_filtered.csv"'})


@app.get("/api/opinions/{case_number}")
def get_opinion(case_number: str) -> dict:
    # Case numbers become filenames; reject separators and traversal.
    if not re.fullmatch(r"[A-Za-z0-9_-]+", case_number):
        raise HTTPException(status_code=400, detail="Invalid case number")
    df = opinions()
    matches = df[df["case_number"].astype(str) == case_number]
    if matches.empty:
        raise HTTPException(status_code=404, detail="Opinion not found")
    text_path = data_root() / "processed" / "text" / f"{case_number}.txt"
    return {"opinion": records(matches.iloc[:1])[0], "text": text_path.read_text(encoding="utf-8") if text_path.is_file() else ""}


@lru_cache(maxsize=16)
def _read_json(path: str, modified_ns: int):
    del modified_ns
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def _optional_json(filename: str, default):
    path = data_root() / "processed" / filename
    return _read_json(str(path), path.stat().st_mtime_ns) if path.is_file() else default


@app.get("/api/case-options")
def case_options() -> dict:
    df = opinions()
    cols = ["case_number", "case_name", "term_year"]
    rows = df[cols].dropna(subset=["case_number", "term_year"]).sort_values("case_name")
    return {"items": records(rows), "updated": opinion_filters()["updated"]}


@app.get("/api/legal/case-options")
def legal_case_options() -> dict:
    """Keep Legal Intelligence selectors in Streamlit's source-data order."""
    df = opinions()
    rows = df[["case_number", "case_name"]].dropna(subset=["case_number"])
    return {"items": records(rows)}


@app.get("/api/cases/{case_number}")
def case_detail(case_number: str) -> dict:
    from utils.justices import normalize_votes_for_bench
    from utils.oral_arguments import find_argument_for_docket
    from utils.charts import bench_diagram

    result = get_opinion(case_number)
    row, text = result["opinion"], result["text"]
    raw = next((item for item in _optional_json("all_opinions.json", []) if item.get("case_number") == case_number), {})
    override_path = data_root() / "citation_overrides.json"
    overrides = _read_json(str(override_path), override_path.stat().st_mtime_ns) if override_path.is_file() else {}
    override = overrides.get(case_number, {})
    candidates = []
    for source in (override if isinstance(override, dict) else {}, row, raw):
        for field in ("reporter_citation", "official_citation", "citation"):
            value = source.get(field)
            if value and str(value).strip().lower() != "nan":
                candidates.append(str(value).strip())
    candidates.append(case_number)
    def citation_rank(value):
        if re.fullmatch(r"\d{4}-\d{3,5}", value):
            return 2
        return 0 if re.fullmatch(r"\d+\s+N\.H\.\s+\d+", value, re.IGNORECASE) else 1
    citation = min(candidates, key=citation_rank)
    votes = normalize_votes_for_bench(raw.get("votes", {}), date_argued=row.get("date_argued"), date_issued=row.get("date_issued"))
    counsel = [fact for fact in _optional_json("brief_counsel.json", {}).get("facts", []) if str(fact.get("docket") or "") == case_number]
    argument = find_argument_for_docket(_optional_json("oral_arguments.json", []), case_number)
    roster = _optional_json("oral_arguments_attorney_stats.json", {}).get("case_attorneys", {}).get(str(argument.get("case_number")), []) if argument else []
    citations = _optional_json("citations.json", {}).get(case_number, {}).get("cites", [])
    cited_by = _optional_json("cited_by.json", {}).get(case_number, [])
    lookup = opinions().set_index("case_number")
    def resolve(numbers):
        resolved = []
        for number in numbers[:20]:
            if number not in lookup.index:
                resolved.append({"case_number": number, "case_name": number, "citation": ""})
                continue
            matched = lookup.loc[number]
            if isinstance(matched, pd.DataFrame):
                matched = matched.iloc[0]
            name = matched.get("case_name")
            cite_options = []
            for source in (overrides.get(number, {}), matched):
                if not hasattr(source, "get"):
                    continue
                for field in ("reporter_citation", "official_citation", "citation"):
                    value = source.get(field)
                    if pd.notna(value) and str(value).strip() and str(value).strip().lower() != "nan":
                        cite_options.append(str(value).strip())
            cite_options.append(number)
            resolved.append({"case_number": number, "case_name": name if isinstance(name, str) else number, "citation": min(cite_options, key=citation_rank)})
        return resolved
    author_line = re.search(r"^(PER CURIAM|[A-Z][A-Z\-]+(?:\s+[A-Z][A-Z\-]+)?,\s+(?:C\.J\.|J\.))[.\s]", text, re.MULTILINE)
    body = text[author_line.end():].lstrip() if author_line else text
    section = re.search(r"(?m)^[ \t]*(?:I\.?\s+)?(?:Background|Facts|BACKGROUND|FACTS|Discussion|DISCUSSION|Procedural History|Procedural|PROCEDURAL|History|HISTORY|Analysis|ANALYSIS|The Facts|The Background)\s*$", body)
    intro = re.sub(r"\n{3,}", "\n\n", (body[:section.start()] if section else body[:3000]).strip())[:4000] if text else ""
    appearance = ""
    appearance_rows = []
    if not counsel and text:
        lines = [line.strip() for line in text.splitlines()[:80]]
        start = next((i + 1 for i, line in enumerate(lines) if line.startswith("Opinion Issued:")), None)
        if start is not None:
            block = []
            for line in lines[start:]:
                if re.match(r"^(PER CURIAM|[A-Z][A-Z\-]+(?:\s+[A-Z][A-Z\-]+)?,\s+(?:C\.J\.|J\.))(?:[.\s]|$)", line) or line.startswith(("I.", "II.")):
                    break
                block.append(line)
            appearance = "\n".join(block).strip()
            paragraphs, current = [], []
            for line in appearance.splitlines():
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
            for paragraph in paragraphs:
                side_match = re.search(r",\s+for\s+(?:the\s+)?(.+?)\.$", paragraph, flags=re.IGNORECASE)
                side = side_match.group(1).strip().capitalize() if side_match else "Other"
                participants = []
                for parenthetical in re.findall(r"\(([^)]+)\)", paragraph):
                    if not re.search(r"\b(on the brief|on the briefs|orally|on the memorandum)\b", parenthetical, re.IGNORECASE):
                        continue
                    participant = re.split(r",?\s+(?:on the brief|on the briefs|orally|on the memorandum)\b", parenthetical, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                    participant = re.sub(r",\s*(?:senior\s+)?(?:assistant\s+)?(?:attorney general|solicitor general|general counsel|attorney).*$", "", participant, flags=re.IGNORECASE).strip()
                    if participant:
                        participants.append(participant)
                if participants:
                    appearance_rows.append({"side": side, "participants": participants})
    def as_list(value):
        try:
            parsed = ast.literal_eval(value) if isinstance(value, str) else value
            return parsed if isinstance(parsed, list) else []
        except (ValueError, SyntaxError):
            return []
    return {**result, "citation": citation, "votes": votes, "bench_chart": json.loads(bench_diagram(votes).to_json()) if votes else None, "vote_colors": VOTE_COLORS, "outcome_color": OUTCOME_COLORS.get(row.get("outcome"), "#607D8B"), "outcome_label": OUTCOME_LABELS.get(row.get("outcome"), str(row.get("outcome") or "").replace("_", " ").title()), "topics": as_list(row.get("topics")), "statutes": as_list(row.get("rsa_citations")), "counsel": counsel, "appearance": appearance, "appearance_rows": appearance_rows, "argument": argument, "roster": roster, "cites": resolve(citations), "cites_count": len(citations), "cited_by": resolve(cited_by), "cited_by_count": len(cited_by), "intro": intro}


def argument_records() -> list[dict]:
    from utils.data_loader import load_oral_arguments
    return load_oral_arguments()


@app.get("/api/arguments/overview")
def arguments_overview() -> dict:
    from utils.oral_arguments import collection_statistics, has_confirmed_argument_date
    rows = argument_records()
    if not rows:
        raise HTTPException(status_code=503, detail="Oral-argument data is unavailable")
    by_year, by_month = Counter(), Counter()
    for row in rows:
        if has_confirmed_argument_date(row):
            parsed = pd.to_datetime(row.get("argument_date"), errors="coerce")
            if pd.notna(parsed) and parsed.year >= 2015:
                by_year[str(parsed.year)] += 1
                by_month[parsed.strftime("%Y-%m")] += 1
    return {"statistics": collection_statistics(rows), "years": sorted(by_year.items()), "months": sorted(by_month.items()),
            "dates": sorted({str(row.get("argument_date")) for row in rows if row.get("argument_date")}),
            "max_duration": max((float(row.get("duration_seconds") or 0) / 60 for row in rows), default=0),
            "max_segments": max((int(row.get("segment_count") or 0) for row in rows), default=0)}


@app.get("/api/arguments/statistics")
def arguments_statistics() -> dict:
    import plotly.express as px
    from utils.data_loader import load_speaker_statistics
    from utils.oral_arguments import has_confirmed_argument_date
    frame = pd.DataFrame([row for row in argument_records() if has_confirmed_argument_date(row)])
    charts = {}
    if frame.empty:
        return {"charts": charts, "speaker_summary": None}
    frame["argument_date"] = pd.to_datetime(frame["argument_date"], errors="coerce")
    frame["argument_year"] = frame["argument_date"].dt.year
    frame["argument_month"] = frame["argument_date"].dt.to_period("M").astype(str)
    frame["duration_minutes"] = pd.to_numeric(frame["duration_seconds"], errors="coerce") / 60
    by_year = frame[frame["argument_year"] >= 2015].groupby("argument_year", as_index=False).size().rename(columns={"size": "arguments"})
    by_month = frame[frame["argument_year"] >= 2015].groupby("argument_month", as_index=False).size().rename(columns={"size": "arguments"})
    def add(name, fig):
        fig.update_layout(plot_bgcolor="white")
        charts[name] = json.loads(fig.to_json())
    fig = px.bar(by_year, x="argument_year", y="arguments", title="Arguments by Year", color_discrete_sequence=["#003057"], labels={"argument_year":"Year argued", "arguments":"Arguments"})
    fig.update_layout(xaxis={"type":"category"}); add("year", fig)
    add("month", px.line(by_month, x="argument_month", y="arguments", markers=True, title="Arguments by Month", color_discrete_sequence=["#b54f2f"], labels={"argument_month":"Month", "arguments":"Arguments"}))
    for key, column, title, color, label in [("duration", "duration_minutes", "Argument Duration Distribution", "#357266", "Duration (minutes)"), ("words", "word_count", "Transcript Word-Count Distribution", "#b54f2f", "Transcript words")]:
        fig = px.histogram(frame, x=column, nbins=12, title=title, color_discrete_sequence=[color], labels={column:label})
        fig.update_layout(showlegend=False); add(key, fig)
    speaker = pd.DataFrame(load_speaker_statistics())
    summary = None
    if not speaker.empty:
        colors = {"Counsel":"#b54f2f", "Justices":"#003057"}
        times = pd.DataFrame({"Role":["Counsel", "Justices"], "Minutes":[speaker["counsel_time"].sum()/60, speaker["justice_time"].sum()/60]})
        add("speaking_time", px.pie(times, values="Minutes", names="Role", title="Speaking Time by Role", color="Role", color_discrete_map=colors))
        pace = pd.DataFrame({"Role":["Counsel", "Justices"], "Words per Minute":[speaker.loc[speaker["counsel_pace_wpm"] > 0, "counsel_pace_wpm"].mean(), speaker.loc[speaker["justice_pace_wpm"] > 0, "justice_pace_wpm"].mean()]})
        fig = px.bar(pace, x="Role", y="Words per Minute", title="Average Speaking Pace", color="Role", color_discrete_map=colors)
        fig.update_layout(showlegend=False); add("speaking_pace", fig)
        summary = {"count":len(speaker), "counsel":float(speaker["counsel_time_pct"].mean()), "justices":float(speaker["justice_time_pct"].mean())}
    return {"charts":charts, "speaker_summary":summary}


@app.get("/api/arguments/trends")
def arguments_trends() -> dict:
    import plotly.express as px
    from utils.data_loader import load_enhanced_statistics
    data = load_enhanced_statistics()
    temporal, complexity = data.get("temporal_trends", {}), data.get("complexity_analysis", {})
    charts = {}
    def add(name, fig):
        fig.update_layout(plot_bgcolor="white")
        charts[name] = json.loads(fig.to_json())
    yearly = pd.DataFrame.from_dict(temporal.get("yearly", {}), orient="index")
    if not yearly.empty:
        yearly.index = yearly.index.astype(int); yearly = yearly.sort_index().reset_index()
        fig = px.bar(yearly, x="index", y="total_arguments", title="Total Arguments Per Year", labels={"index":"Year", "total_arguments":"Arguments"}); fig.update_layout(showlegend=False, xaxis={"type":"category"}); add("yearly", fig)
        durations = yearly.rename(columns={"avg_duration_min":"Avg Duration Min", "median_duration_min":"Median Duration Min"})
        fig = px.line(durations, x="index", y=["Avg Duration Min", "Median Duration Min"], title="Argument Duration Trends", labels={"index":"Year", "value":"Minutes", "variable":"Metric"}); fig.update_layout(xaxis={"type":"category"}); add("yearly_duration", fig)
    growth = temporal.get("yoy_growth", {})
    if growth:
        g = pd.DataFrame.from_dict(growth, orient="index", columns=["Growth %"]); g.index = g.index.astype(int); g = g.sort_index().reset_index()
        fig = px.bar(g, x="index", y="Growth %", title="Year-over-Year Change in Oral Argument Volume", labels={"index":"Year"}, color="Growth %", color_continuous_scale=["red", "white", "green"]); fig.update_layout(xaxis={"type":"category"}); add("growth", fig)
    monthly = pd.DataFrame.from_dict(temporal.get("monthly", {}), orient="index")
    if not monthly.empty:
        monthly.index = monthly.index.astype(int); monthly = monthly.sort_index(); monthly["Month"] = [datetime(2000, i, 1).strftime("%b") for i in monthly.index]
        fig = px.bar(monthly, x="Month", y="total_arguments", title="Arguments by Month (All Years)", labels={"total_arguments":"Total Arguments"}); fig.update_layout(showlegend=False); add("monthly", fig)
    quarterly = pd.DataFrame.from_dict(temporal.get("quarterly", {}), orient="index")
    if not quarterly.empty:
        quarterly.index = [f"Q{i}" for i in quarterly.index.astype(int)]; add("quarterly", px.pie(quarterly, values="total_arguments", names=quarterly.index, title="Arguments by Quarter"))
    if complexity:
        c = pd.DataFrame.from_dict(complexity, orient="index").reindex(["Simple", "Moderate", "Complex", "Very Complex"])
        fig = px.bar(c.reset_index(), x="index", y="count", title="Cases by Complexity", labels={"index":"Complexity", "count":"Number of Cases"}, color="count", color_continuous_scale="Reds", text="count"); fig.update_traces(texttemplate="%{text:,}", textposition="outside"); fig.update_layout(showlegend=False); add("complexity", fig)
        d = c[["min_duration", "avg_duration", "max_duration"]].rename(columns={"min_duration":"Minimum Duration", "avg_duration":"Average Duration", "max_duration":"Maximum Duration"}).reset_index()
        add("complexity_duration", px.bar(d, x="index", y=["Minimum Duration", "Average Duration", "Maximum Duration"], title="Duration Range by Complexity", labels={"index":"Complexity", "value":"Minutes", "variable":"Duration"}, barmode="group"))
    types = data.get("case_parties", {}).get("case_types", {})
    if types: add("case_types", px.pie(values=list(types.values()), names=list(types.keys()), title="Distribution of Case Types"))
    networks = data.get("attorney_networks", {}); firms = networks.get("top_firms", [])
    if firms:
        fig = px.bar(pd.DataFrame(firms[:15]), x="attorney_count", y="firm", orientation="h", title="Largest Firms by Attorney Count", labels={"attorney_count":"Number of Attorneys", "firm":""}, color="attorney_count", color_continuous_scale="Reds"); fig.update_layout(yaxis={"categoryorder":"total ascending"}); add("firms", fig)
    return {"available":bool(temporal), "charts":charts, "complexity":complexity, "solo_count":len(networks.get("solo_practitioners", []))}


def _filter_arguments(rows, q, dates, year_min, year_max, duration_min, duration_max, segments_min, segments_max, case_type):
    from utils.oral_arguments import search_oral_arguments
    result = search_oral_arguments(rows, q)
    def keep(row):
        day = str(row.get("argument_date") or "")
        try:
            year = int(day[:4])
        except ValueError:
            return False
        duration = float(row.get("duration_seconds") or 0) / 60
        segments = int(row.get("segment_count") or 0)
        name = str(row.get("case_name") or "").lower()
        state = "state v." in name or "state of new hampshire v." in name
        kind = case_type == "all" or (case_type == "criminal" and state) or (case_type == "civil" and " v. " in name and "state v." not in name) or (case_type == "family" and ("in re" in name or "in the matter" in name))
        return (not dates or day in dates) and year_min <= year <= year_max and duration > 0 and duration_min <= duration <= duration_max and segments > 0 and segments_min <= segments <= segments_max and kind
    return [row for row in result if keep(row)]


@app.get("/api/arguments")
def list_arguments(q: str = Query(default="", max_length=300), date: list[str] = Query(default=[]),
                   year_min: int = 2000, year_max: int = 2100, duration_min: float = 0, duration_max: float = 10000,
                   segments_min: int = 0, segments_max: int = 100000, case_type: str = Query(default="all", pattern="^(all|criminal|civil|family)$"),
                   limit: int = Query(default=24, ge=1, le=100)) -> dict:
    rows = argument_records()
    filtered = _filter_arguments(rows, q, date, year_min, year_max, duration_min, duration_max, segments_min, segments_max, case_type)
    items = [{key: value for key, value in row.items() if key != "transcript_text"} | {"snippet": row.get("_snippet") or str(row.get("transcript_text") or "")[:310]} for row in filtered[:limit]]
    return {"count": len(filtered), "total": len(rows), "items": items}


@app.get("/api/arguments.csv")
def download_arguments() -> Response:
    return Response(pd.DataFrame(argument_records()).to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="oral_arguments.csv"'})


def argument_detail(case_number: str) -> dict:
    from utils.oral_arguments import find_argument_for_docket
    if not re.fullmatch(r"[A-Za-z0-9_-]+", case_number):
        raise HTTPException(status_code=400, detail="Invalid case number")
    rows = argument_records()
    row = next((item for item in rows if str(item.get("case_number")) == case_number), None) or find_argument_for_docket(rows, case_number)
    if not row:
        raise HTTPException(status_code=404, detail="Argument not found")
    key = str(row["case_number"])
    if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise HTTPException(status_code=400, detail="Invalid argument identifier")
    def artifact(folder, extension):
        path = data_root() / "processed" / "oral_arguments" / folder / f"{key}.{extension}"
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    speaker = next((item for item in _optional_json("oral_arguments_speaker_stats.json", []) if item.get("case_number") == key), None)
    attorneys = _optional_json("oral_arguments_attorney_stats.json", {})
    case_attorneys = attorneys.get("case_attorneys", {}).get(key, [])
    names = {item.get("name") for item in case_attorneys}
    return {"record": {k: v for k, v in row.items() if k != "transcript_text"}, "text": artifact("text", "txt"), "markdown": artifact("markdown", "md"),
            "speakers": speaker, "attorneys": case_attorneys, "attorney_stats": [item for item in attorneys.get("attorney_stats", []) if item.get("attorney_name") in names]}


def _list_field(value) -> list:
    try:
        value = ast.literal_eval(value) if isinstance(value, str) else value
        return value if isinstance(value, list) else []
    except (ValueError, SyntaxError):
        return []


def _case_group(row) -> str:
    kind = str(row.get("case_type") or "").strip().lower()
    topics, statutes = _list_field(row.get("topics")), _list_field(row.get("rsa_citations"))
    if kind in {"family/domestic", "domestic/family", "family", "domestic"}:
        return "family/domestic"
    if kind in {"criminal", "civil"}:
        return kind
    if "family_law" in topics or "domestic_violence" in topics:
        return "family/domestic"
    if "criminal" in topics:
        return "criminal"
    for value in statutes:
        if re.match(r"RSA\s+(?:169-C|173-B|458|461-A)", str(value), re.IGNORECASE):
            return "family/domestic"
        if re.match(r"RSA\s+(?:6\d{2}|265-A)", str(value), re.IGNORECASE):
            return "criminal"
    return "civil"


def _case_rows(df):
    columns = [c for c in ("citation", "case_number", "case_name", "date_issued", "outcome", "author_display", "pdf_url") if c in df.columns]
    return records(df[columns])


def _topic_profile_frames(key: str, label: str):
    from utils.data_loader import load_argument_dispositions, load_argument_participants, load_argument_topics
    dispositions, participants, topics = load_argument_dispositions(), load_argument_participants(), load_argument_topics()
    if dispositions.empty or topics.empty:
        return None
    ids = set(topics.loc[topics["topic"].isin([key, label]), "argument_id"])
    matches = dispositions[dispositions["argument_id"].isin(ids)].copy()
    if matches.empty:
        return None
    people = participants[participants["argument_id"].isin(ids)] if not participants.empty else pd.DataFrame()
    return matches, people


def _topic_profile(key: str, label: str) -> dict | None:
    import plotly.express as px
    from utils.case_resolution import RESOLUTION_LABELS
    frames = _topic_profile_frames(key, label)
    if frames is None:
        return None
    matches, people = frames
    resolved = matches[matches["resolution_type"].isin(["opinion", "case_order", "3jx_order", "multiple"])]
    days = pd.to_numeric(resolved["days_to_disposition"], errors="coerce").dropna()
    count = lambda series: [{"name": str(k), "count": int(v)} for k, v in series.value_counts().items()]
    timing = []
    if not days.empty:
        for kind, group in resolved.groupby("resolution_type"):
            valid = pd.to_numeric(group["days_to_disposition"], errors="coerce").dropna()
            if not valid.empty:
                timing.append({"name": kind, "median": float(valid.median()), "count": len(valid)})
    charts = {}
    colors = {"opinion":"#7E57C2", "case_order":"#005A9C", "3jx_order":"#4A7C59", "multiple":"#E09F3E", "needs_review":"#FFA726", "unmatched":"#9E9E9E"}
    def add(name, fig, reverse=False):
        fig.update_layout(plot_bgcolor="white", **({"yaxis":{"autorange":"reversed"}} if reverse else {}))
        charts[name] = json.loads(fig.to_json())
    resolution_counts = matches["resolution_type"].value_counts().reset_index()
    resolution_counts.columns = ["resolution_type", "count"]
    resolution_counts["label"] = resolution_counts["resolution_type"].map(RESOLUTION_LABELS)
    add("resolution", px.pie(resolution_counts, names="label", values="count", title=f"{label} Disposition Types", color="resolution_type", color_discrete_map=colors, hole=0.3))
    yearly = matches.groupby(["term_year", "resolution_type"]).size().reset_index(name="count")
    if not yearly.empty:
        add("yearly", px.bar(yearly, x="term_year", y="count", color="resolution_type", title=f"{label} Disposition Trend", labels={"term_year":"Year", "count":"Arguments"}, color_discrete_map=colors, barmode="stack"))
    timing_data = resolved.copy()
    timing_data["days_to_disposition"] = pd.to_numeric(timing_data["days_to_disposition"], errors="coerce")
    timing_data = timing_data[timing_data["days_to_disposition"].notna()]
    if not timing_data.empty:
        add("timing", px.histogram(timing_data, x="days_to_disposition", nbins=25, title=f"{label} Days to Disposition", labels={"days_to_disposition":"Days", "count":"Arguments"}, color_discrete_sequence=["#005A9C"]))
        timing_by_type = timing_data.groupby("resolution_type")["days_to_disposition"].agg(["median", "count"]).reset_index().sort_values("median", ascending=False)
        timing_by_type["label"] = timing_by_type["resolution_type"].map(RESOLUTION_LABELS)
        fig = px.bar(timing_by_type, x="median", y="label", orientation="h", title="Median Days by Disposition Type", labels={"median":"Median Days", "label":"Disposition"}, color_discrete_sequence=["#005A9C"], text="count")
        fig.update_traces(texttemplate="n=%{text}", textposition="outside"); add("timing_type", fig, True)
    case_types = matches["case_type"].value_counts().reset_index(); case_types.columns = ["Case Type", "Count"]
    if not case_types.empty:
        add("case_types", px.bar(case_types, x="Count", y="Case Type", orientation="h", title=f"{label} Arguments by Case Type", color_discrete_sequence=["#7E57C2"]), True)
    for key_name, column, heading, color in (("attorneys", "attorney_name", "Attorney", "#4A7C59"), ("firms", "firm", "Firm", "#E09F3E")):
        if not people.empty:
            counts = people[column].value_counts().head(15).reset_index(); counts.columns = [heading, "Arguments"]
            if not counts.empty:
                add(key_name, px.bar(counts, x="Arguments", y=heading, orientation="h", title=f"Top 15 {heading}s Arguing {label}", color_discrete_sequence=[color]), True)
    outcome_counts = resolved["outcome"].value_counts().reset_index(); outcome_counts.columns = ["Outcome", "Count"]
    if not outcome_counts.empty:
        add("outcomes", px.pie(outcome_counts, names="Outcome", values="Count", title=f"{label} Outcomes", color_discrete_sequence=px.colors.sequential.Blues_r, hole=0.3))
    return {"arguments": len(matches), "resolved": len(resolved), "median_days": float(days.median()) if not days.empty else None,
            "resolution": count(matches["resolution_type"]), "case_types": count(matches["case_type"]),
            "percentiles": {str(q): float(days.quantile(q)) for q in (0.25, 0.5, 0.75, 0.9)} if not days.empty else {},
            "timing": timing, "days": days.tolist(),
            "yearly": records(matches.groupby(["term_year", "resolution_type"]).size().reset_index(name="count")),
            "attorneys": count(people["attorney_name"])[:15] if not people.empty else [], "firms": count(people["firm"])[:15] if not people.empty else [],
            "outcomes": records(outcome_counts), "charts": charts}


@app.get("/api/topics/dispositions.csv")
def download_topic_dispositions(topic: str = Query(min_length=1, max_length=100)) -> Response:
    path = data_root() / "topic_taxonomy.json"
    taxonomy = _read_json(str(path), path.stat().st_mtime_ns) if path.is_file() else {}
    label = taxonomy.get(topic, {}).get("label", topic.replace("_", " ").title())
    frames = _topic_profile_frames(topic, label)
    if frames is None:
        raise HTTPException(status_code=404, detail="Topic disposition data not found")
    columns = ["argument_id", "case_name", "argument_date", "term_year", "resolution_type", "disposition_date", "days_to_disposition", "outcome", "case_type", "lower_court", "author"]
    filename = re.sub(r"[^A-Za-z0-9_-]+", "_", label.replace("/", "-"))
    return Response(frames[0][columns].to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="topic_{filename}_dispositions.csv"'})


@app.get("/api/topics")
def topics_page(year_min: int = 2000, year_max: int = 2100, topic: list[str] = Query(default=[]), rsa: str = Query(default="", max_length=100)) -> dict:
    import plotly.express as px
    df = opinions()
    filtered = df[df["term_year"].between(year_min, year_max)].copy()
    taxonomy_path = data_root() / "topic_taxonomy.json"
    taxonomy = _read_json(str(taxonomy_path), taxonomy_path.stat().st_mtime_ns) if taxonomy_path.is_file() else {}
    counts = Counter(item for value in filtered["topics"].dropna() for item in _list_field(value))
    label = lambda key: taxonomy.get(key, {}).get("label", str(key).replace("_", " ").title())
    topic_list = [{"key": key, "label": label(key), "count": count} for key, count in counts.most_common()]
    selected = filtered[filtered["topics"].apply(lambda value: any(item in _list_field(value) for item in topic))] if topic else filtered.iloc[0:0]
    rsa_rows = filtered[filtered["rsa_citations"].fillna("").astype(str).str.contains(rsa.strip(), case=False, regex=False)] if rsa.strip() else filtered.iloc[0:0]
    def summary(frame):
        return {"count": len(frame), "outcomes": [{"key": str(k), "label": OUTCOME_LABELS.get(k, str(k).replace("_", " ").title()), "color": OUTCOME_COLORS.get(k, "#607D8B"), "count": int(v)} for k, v in frame["outcome"].value_counts().items()],
                "years": [{"year": int(k), "count": int(v)} for k, v in frame.groupby("term_year").size().items()], "items": _case_rows(frame)}
    def figure_json(figure):
        return json.loads(figure.to_json())
    colors = {OUTCOME_LABELS.get(k, k.replace("_", " ").title()): v for k, v in OUTCOME_COLORS.items()}
    def outcome_chart(frame, title, compact=False):
        counts = frame["outcome"].value_counts().reset_index()
        counts.columns = ["outcome", "count"]
        counts["label"] = counts["outcome"].map(lambda value: OUTCOME_LABELS.get(value, str(value).replace("_", " ").title()))
        fig = px.pie(counts, values="count", names="label", color="label", color_discrete_map=colors, title=title)
        if compact:
            fig.update_traces(textinfo="none")
            fig.update_layout(plot_bgcolor="white", height=320, margin={"l":10,"r":10,"t":55,"b":85}, legend=dict(orientation="h", yanchor="top", y=-0.28, xanchor="left", x=0), title=dict(x=0.0,xanchor="left"))
        return figure_json(fig)
    charts = {}
    if topic_list:
        top = pd.DataFrame(topic_list[:15]).rename(columns={"label":"topic_label"})
        fig = px.bar(top, x="count", y="topic_label", orientation="h", color_discrete_sequence=["#003057"], title="Opinions Per Topic")
        fig.update_layout(plot_bgcolor="white", yaxis={"autorange":"reversed"})
        charts["topics"] = figure_json(fig)
    if topic:
        charts["outcomes"] = outcome_chart(selected, "Outcome Distribution")
        years = selected.groupby("term_year").size().reset_index(name="count")
        fig = px.line(years, x="term_year", y="count", markers=True, title="Topic Trend Over Years", labels={"term_year":"Year","count":"Count"}, color_discrete_sequence=["#003057"])
        fig.update_layout(plot_bgcolor="white"); charts["trend"] = figure_json(fig)
    if not rsa_rows.empty:
        years = rsa_rows.groupby("term_year").size().reset_index(name="count")
        fig = px.bar(years, x="term_year", y="count", color_discrete_sequence=["#C8960C"], title=f"RSA {rsa.strip()} — Litigation Timeline")
        fig.update_layout(plot_bgcolor="white"); charts["rsa"] = figure_json(fig)
    groups = {}
    grouped = filtered.assign(_case_group=filtered.apply(_case_group, axis=1))
    for name, display, color in (("criminal", "Criminal", "#8b0000"), ("civil", "Civil", "#003057"), ("family/domestic", "Family/Domestic", "#2e7d32")):
        frame = grouped[grouped["_case_group"] == name]
        group = summary(frame)
        group["items"] = group["items"][:20]
        group["topics"] = [{"name": str(k).replace("_", " ").title(), "count": v} for k, v in Counter(item for value in frame["topics"].dropna() for item in _list_field(value)).most_common(8)]
        group["charts"] = {}
        if not frame.empty:
            group["charts"]["outcomes"] = outcome_chart(frame, f"{display} — Outcomes", compact=True)
            if group["topics"]:
                fig = px.bar(pd.DataFrame(group["topics"]).rename(columns={"name":"topic"}), x="count", y="topic", orientation="h", title=f"{display} Topics", color_discrete_sequence=[color])
                fig.update_layout(plot_bgcolor="white", height=320, margin={"l":10,"r":10,"t":55,"b":45}, title=dict(x=0.0,xanchor="left"), yaxis={"autorange":"reversed"})
                group["charts"]["topics"] = figure_json(fig)
        groups[name] = group
    return {"topics": topic_list, "selected": summary(selected), "profile": _topic_profile(topic[0], label(topic[0])) if len(topic) == 1 else None,
            "rsa": summary(rsa_rows), "groups": groups, "charts": charts, "updated": opinion_filters()["updated"]}


@app.get("/api/topics/rsa")
def topics_rsa(year_min: int = 2000, year_max: int = 2100, q: str = Query(default="", max_length=100)) -> dict:
    import plotly.express as px
    df = opinions()
    filtered = df[df["term_year"].between(year_min, year_max)]
    query = q.strip()
    rows = filtered[filtered["rsa_citations"].fillna("").astype(str).str.contains(query, case=False, regex=False)] if query else filtered.iloc[0:0]
    outcomes = [{"key":str(k), "count":int(v)} for k,v in rows["outcome"].value_counts().items()]
    chart = None
    if not rows.empty:
        years = rows.groupby("term_year").size().reset_index(name="count")
        figure = px.bar(years, x="term_year", y="count", color_discrete_sequence=["#C8960C"], title=f"RSA {query} — Litigation Timeline")
        figure.update_layout(plot_bgcolor="white")
        chart = json.loads(figure.to_json())
    return {"count":len(rows), "items":_case_rows(rows), "outcomes":outcomes, "chart":chart}


@lru_cache(maxsize=2)
def _read_orders(root: str, orders_mtime: int, jx_mtime: int) -> pd.DataFrame:
    from pathlib import Path
    del orders_mtime, jx_mtime
    directory = Path(root) / "processed"
    frames = []
    regular = directory / "case_orders.csv"
    three_jx = directory / "3jx_orders.csv"
    if regular.is_file():
        df = pd.read_csv(regular, low_memory=False, encoding="utf-8")
        df["order_source"] = "case_order"
        frames.append(df)
    if three_jx.is_file():
        df = pd.read_csv(three_jx, low_memory=False, encoding="utf-8")
        if "year" in df.columns and "term_year" not in df.columns:
            df["term_year"] = df["year"]
        df["order_source"] = df["opinion_type"].fillna("3jx_order") if "opinion_type" in df.columns else "3jx_order"
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    frame = pd.concat(frames, ignore_index=True, sort=False)
    frame = frame[frame["case_name"].fillna("").str.lower().ne("request a transcript")]
    frame = frame[frame["case_number"].fillna("").astype(str).str.lower().ne("transcript-instructions")]
    # The two feeds contain both ISO and slash-formatted dates. Normalize them
    # before sorting and serialization, as the Streamlit loader does.
    frame["date_issued"] = pd.to_datetime(frame["date_issued"], errors="coerce", format="mixed")
    return frame


def orders() -> pd.DataFrame:
    root = data_root()
    path = root / "processed" / "case_orders.csv"
    jx = root / "processed" / "3jx_orders.csv"
    return _read_orders(str(root), path.stat().st_mtime_ns if path.exists() else 0, jx.stat().st_mtime_ns if jx.exists() else 0)


def _filter_orders(frame, years, types, sources, q):
    filtered = frame
    if years:
        filtered = filtered[filtered["term_year"].isin(years)]
    if types:
        filtered = filtered[filtered["case_type"].isin(types)]
    if sources:
        filtered = filtered[filtered["order_source"].isin(sources)]
    if q:
        filtered = filtered[filtered["case_name"].fillna("").astype(str).str.contains(q, case=False, regex=False)]
    return (filtered.assign(_date_sort=pd.to_datetime(filtered["date_issued"], errors="coerce"),
                            _year_sort=pd.to_numeric(filtered["term_year"], errors="coerce"),
                            _case_sort=filtered["case_number"].astype(str))
            .sort_values(["_date_sort", "_year_sort", "_case_sort"], ascending=[False, False, False], na_position="last")
            .drop(columns=["_date_sort", "_year_sort", "_case_sort"]))


@app.get("/api/orders/filters")
def order_filters() -> dict:
    df = orders()
    if df.empty:
        raise HTTPException(status_code=503, detail="Case-order data is unavailable")
    return {"years": sorted(int(value) for value in df["term_year"].dropna().unique()),
            "types": sorted(str(value) for value in df["case_type"].dropna().unique()),
            "sources": sorted(str(value) for value in df["order_source"].dropna().unique()),
            "updated": opinion_filters()["updated"]}


@app.get("/api/orders")
def list_orders(year: list[int] = Query(default=[]), case_type: list[str] = Query(default=[]), source: list[str] = Query(default=[]),
                q: str = Query(default="", max_length=300), offset: int = Query(default=0, ge=0), limit: int = Query(default=5000, ge=1, le=5000),
                sort: str = Query(default="", pattern="^(|case_number|case_name|date_issued|case_type|outcome|vote_string|order_source)$"),
                direction: str = Query(default="asc", pattern="^(asc|desc)$")) -> dict:
    import plotly.express as px
    df = orders()
    if df.empty:
        raise HTTPException(status_code=503, detail="Case-order data is unavailable")
    filtered = _filter_orders(df, year, case_type, source, q)
    if isinstance(sort, str) and sort and sort in filtered.columns:
        # Sort the complete filtered set before pagination, with empty values
        # last. Dates need parsing because source CSVs contain mixed formats.
        values = (pd.to_datetime(filtered[sort], errors="coerce") if sort == "date_issued"
                  else filtered[sort].fillna("").astype(str).str.casefold().replace("", pd.NA))
        filtered = filtered.assign(_display_sort=values).sort_values("_display_sort", ascending=direction == "asc", na_position="last", kind="stable").drop(columns="_display_sort")
    charts = {}
    if not filtered.empty:
        type_counts = filtered["case_type"].value_counts().reset_index()
        type_counts.columns = ["case_type", "count"]
        type_counts["case_type_label"] = type_counts["case_type"].astype(str).str.replace("_", " ").str.title()
        figure = px.bar(type_counts, x="case_type_label", y="count", color_discrete_sequence=["#003057"],
                        labels={"case_type_label":"Case Type", "count":"Orders"}, title="Case Type Distribution")
        figure.update_layout(plot_bgcolor="white", xaxis_tickangle=-20)
        charts["types"] = json.loads(figure.to_json())
        year_counts = filtered.groupby("term_year").size().reset_index(name="count")
        figure = px.line(year_counts, x="term_year", y="count", markers=True,
                         labels={"term_year":"Year", "count":"Orders"}, title="Orders Per Year", color_discrete_sequence=["#003057"])
        figure.update_layout(plot_bgcolor="white")
        charts["years"] = json.loads(figure.to_json())
    return {"total": len(df), "count": len(filtered), "items": records(filtered.iloc[offset:offset+limit]),
            "types": [{"name": str(k), "count": int(v)} for k, v in filtered["case_type"].value_counts().items()],
            "years": [{"year": int(k), "count": int(v)} for k, v in filtered.groupby("term_year").size().items()], "charts": charts}


@app.get("/api/orders.csv")
def download_orders(year: list[int] = Query(default=[]), case_type: list[str] = Query(default=[]), source: list[str] = Query(default=[]),
                    q: str = Query(default="", max_length=300)) -> Response:
    df = orders()
    if df.empty:
        raise HTTPException(status_code=503, detail="Case-order data is unavailable")
    return Response(_filter_orders(df, year, case_type, source, q).to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="nh_sc_case_orders_filtered.csv"'})


_JUDGE_END = re.compile(r"\s*\([A-Za-z\s.'\u2018\u2019-]+,\s*(?:C\.J\.|JJ\.|J\.)\)\s*$")
_JUDGE_IN_COURT = re.compile(r"\(([A-Za-z\s.'\u2018\u2019-]+),\s*(?:C\.J\.|JJ\.|J\.)\)")
_TRIAL_OUTCOMES = ["Affirmed", "Remanded", "Affirmed & Remanded", "Reversed & Remanded", "Reversed", "Vacated", "Dismissed"]


def _trial_frame(years: list[int]) -> pd.DataFrame:
    df = opinions()
    if years:
        df = df[df["term_year"].isin(years)]
    df = df[df["lower_court"].notna()].copy()
    def clean_court(value):
        value = re.sub(r"\s+", " ", _JUDGE_END.sub("", str(value)).split(";")[0]).strip()
        return "Family Court" if "family court" in value.lower() and "circuit" not in value.lower() else value
    def court_type(value):
        lower = value.lower()
        if "circuit" in lower:
            for division in ("family", "district", "probate"):
                if division in lower:
                    return f"Circuit Court – {division.title()} Division"
            return "Circuit Court"
        if "superior" in lower:
            return "Superior Court"
        if "probate" in lower:
            return "Probate Court"
        return value
    df["court_base"] = df["lower_court"].map(clean_court)
    df["judge"] = df["lower_court"].map(lambda value: match.group(1).strip() if (match := _JUDGE_IN_COURT.search(str(value))) else None)
    df["court_type"] = df["court_base"].map(court_type)
    df["outcome_label"] = df["outcome"].map(lambda value: OUTCOME_LABELS.get(value, str(value).replace("_", " ").title()) if pd.notna(value) else None)
    return df


def _trial_breakdown(frame: pd.DataFrame, columns: list[str], min_cases: int = 0) -> list[dict]:
    if frame.empty:
        return []
    pivot = frame.groupby(columns + ["outcome_label"]).size().unstack(fill_value=0).reset_index()
    outcome_columns = [column for column in pivot.columns if column not in columns]
    pivot["Total"] = pivot[outcome_columns].sum(axis=1)
    pivot = pivot[pivot["Total"] >= min_cases]
    if columns == ["court_type", "court_base"]:
        pivot = pivot.sort_values(["court_type", "Total"], ascending=[True, False])
    else:
        pivot = pivot.sort_values("Total", ascending=False)
    for label in _TRIAL_OUTCOMES:
        if label not in pivot:
            pivot[label] = 0
    return records(pivot)


def _trial_chart(frame: pd.DataFrame, field: str, title: str, minimum: int, *, vertical: bool, sort_by_total: bool, height: int) -> dict | None:
    import plotly.express as px
    grouped = frame.groupby([field, "outcome_label"]).size().reset_index(name="count")
    if grouped.empty:
        return None
    totals = grouped.groupby(field)["count"].sum().reset_index(name="total")
    if sort_by_total:
        totals = totals.sort_values("total", ascending=False)
    order = totals.loc[totals["total"] >= minimum, field].tolist()
    grouped = grouped[grouped[field].isin(order)]
    if grouped.empty:
        return None
    color_map = {OUTCOME_LABELS.get(key, key): value for key, value in OUTCOME_COLORS.items()}
    figure = px.bar(grouped, x=field if vertical else "count", y="count" if vertical else field,
                    color="outcome_label", orientation="v" if vertical else "h", title=title,
                    category_orders={"outcome_label": _TRIAL_OUTCOMES, field: order}, color_discrete_map=color_map,
                    height=max(height, len(order) * 120 if field == "court_type" else len(order) * 30 + 120 if not vertical else height))
    figure.update_traces(text=None, hovertemplate=("%{x}<br>%{fullData.name}: %{y}<extra></extra>" if vertical else "%{y}<br>%{fullData.name}: %{x}<extra></extra>"))
    figure.update_layout(plot_bgcolor="white", barmode="stack", legend_title_text="Outcome",
                         legend=dict(orientation="h", yanchor="top", y=-0.25 if vertical else -0.2, xanchor="left", x=0, font=dict(size=11)),
                         xaxis=dict(title="" if vertical else "Number of Cases", automargin=True, **({"tickangle":-32, "tickfont":{"size":11}} if vertical else {})),
                         yaxis=dict(title="Number of Cases" if vertical else "", automargin=True, **({} if vertical else {"autorange":"reversed", "tickfont":{"size":11}})),
                         margin={"l":10 if vertical else 180, "r":10, "t":50, "b":150 if vertical else 90}, hovermode="x" if vertical else "y")
    return json.loads(figure.to_json())


@app.get("/api/trial-courts")
def trial_courts(year: list[int] = Query(default=[]), min_cases: int = Query(default=3, ge=2, le=10)) -> dict:
    df = _trial_frame(year)
    outcomes = df[df["outcome_label"].notna()].copy()
    outcomes["court_group"] = outcomes["court_type"].map(lambda value: "Circuit Court" if value.startswith("Circuit Court") else value)
    judges = _trial_breakdown(outcomes[outcomes["judge"].notna()], ["judge"], min_cases)
    for row in judges:
        row["Affirm %"] = round(row["Affirmed"] / row["Total"] * 100, 1)
        row["Reversal %"] = round((row["Reversed"] + row["Reversed & Remanded"]) / row["Total"] * 100, 1)
    affirmed = int(outcomes["outcome"].eq("affirmed").sum())
    reversed_count = int(outcomes["outcome"].isin(["reversed", "reversed_and_remanded"]).sum())
    charts = {
        "court_types": _trial_chart(outcomes, "court_type", "Case Outcomes by Court Type", min_cases, vertical=True, sort_by_total=False, height=520),
        "court_groups": _trial_chart(outcomes, "court_group", "Case Outcomes by Court", min_cases, vertical=True, sort_by_total=True, height=360),
        "judges": _trial_chart(outcomes[outcomes["judge"].notna()], "judge", "Case Outcomes by Trial Judge", min_cases, vertical=False, sort_by_total=True, height=420),
    }
    return {"total": len(df), "affirmed": affirmed, "reversed": reversed_count,
            "affirm_rate": affirmed / len(outcomes) * 100 if len(outcomes) else 0,
            "court_types": _trial_breakdown(outcomes, ["court_type"], min_cases),
            "individual_courts": _trial_breakdown(outcomes, ["court_type", "court_base"]),
            "court_groups": _trial_breakdown(outcomes, ["court_group"], min_cases),
            "circuit_courts": _trial_breakdown(outcomes[outcomes["court_group"] == "Circuit Court"], ["court_base"]),
            "judges": judges, "charts": charts, "updated": opinion_filters()["updated"]}


@app.get("/api/trial-courts.csv")
def download_trial_courts(year: list[int] = Query(default=[])) -> Response:
    return Response(_trial_frame(year).to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="nh_sc_trial_courts_filtered.csv"'})


def _justices_metadata() -> dict:
    path = data_root() / "justices.json"
    values = _read_json(str(path), path.stat().st_mtime_ns) if path.is_file() else []
    return {item["key"]: item for item in values}


@app.get("/api/about")
def about() -> dict:
    df = opinions()
    years = pd.to_numeric(df["term_year"], errors="coerce").dropna()
    return {"justices": list(_justices_metadata().values()), "total": len(df),
            "year_min": int(years.min()) if not years.empty else None,
            "year_max": int(years.max()) if not years.empty else None,
            "updated": opinion_filters()["updated"]}


@app.get("/api/justices/filters")
def justices_filters() -> dict:
    metadata = _justices_metadata()
    active = sorted((j for j in metadata.values() if j.get("is_active")), key=lambda x: (x["role"] != "chief_justice", x["last_name"]))
    return {"justices": [{"key": j["key"], "label": JUSTICE_DISPLAY.get(j["key"], j["key"])} for j in active], "updated": opinion_filters()["updated"]}


@app.get("/api/justices")
def justice_page(justice: str = Query(min_length=1, max_length=80), year_min: int = 2000, year_max: int = 2100) -> dict:
    import plotly.express as px
    from utils.charts import agreement_heatmap, authorship_bar
    metadata = _justices_metadata()
    if justice not in metadata or not metadata[justice].get("is_active"):
        raise HTTPException(status_code=404, detail="Justice not found")
    meta = metadata[justice]
    appointed = pd.to_datetime(meta.get("date_appointed"), errors="coerce")
    df = opinions()
    df = df[df["term_year"].between(year_min, year_max)]
    authored = df[df["author"] == justice].copy()
    if pd.notna(appointed):
        authored = authored[pd.to_datetime(authored["date_issued"], errors="coerce") >= appointed]
    cases = []
    matrix_co = {a: Counter() for a in JUSTICE_KEYS}
    matrix_agree = {a: Counter() for a in JUSTICE_KEYS}
    for rec in _optional_json("all_opinions.json", []):
        year = rec.get("term_year") or rec.get("citation_year")
        try:
            if not year or not year_min <= int(year) <= year_max:
                continue
        except (TypeError, ValueError):
            continue
        votes = rec.get("votes") or {}
        present = {key: votes.get(key, {}).get("vote", "not_participating") for key in JUSTICE_KEYS}
        present = {key: vote for key, vote in present.items() if vote not in ("not_participating", "recused", "disqualified")}
        for a, vote_a in present.items():
            for b, vote_b in present.items():
                if a != b:
                    matrix_co[a][b] += 1
                    if vote_a == vote_b:
                        matrix_agree[a][b] += 1
        issued = pd.to_datetime(rec.get("date_issued"), errors="coerce")
        if pd.notna(appointed) and ((pd.notna(issued) and issued < appointed) or (pd.isna(issued) and int(year) < appointed.year)):
            continue
        cases.append({"case_name": rec.get("case_name", ""), "citation": rec.get("citation") or rec.get("case_number") or "unknown",
                      "case_number": rec.get("case_number", ""), "date_issued": rec.get("date_issued", ""),
                      "vote": votes.get(justice, {}).get("vote", "not_participating"), "outcome": rec.get("outcome", "")})
    matrix = [[1.0 if a == b else matrix_agree[a][b] / matrix_co[a][b] if matrix_co[a][b] else 0.0 for b in JUSTICE_KEYS] for a in JUSTICE_KEYS]
    pairs = [{"a": JUSTICE_DISPLAY.get(a, a), "b": JUSTICE_DISPLAY.get(b, b), "rate": matrix[i][j]} for i, a in enumerate(JUSTICE_KEYS) for j, b in enumerate(JUSTICE_KEYS) if j > i]
    pairs.sort(key=lambda item: item["rate"], reverse=True)
    participation = sum(case["vote"] in ("majority", "dissent", "concur_separate") for case in cases)
    dissent = sum(case["vote"] == "dissent" for case in cases)
    authored_by_year = [{"year": int(year), "count": int(count)} for year, count in authored.groupby("term_year").size().items()]
    authors = [{"name": JUSTICE_DISPLAY.get(key, key), "count": int(value)} for key, value in df[df["author"] != "per_curiam"]["author"].value_counts().items()]
    per_curiam = df[df["author"] == "per_curiam"].groupby("term_year").size()
    yearly = df.groupby("term_year").size()
    name = JUSTICE_DISPLAY.get(justice, justice)
    charts = {}
    if not authored.empty:
        per_year = authored.groupby("term_year").size().reset_index(name="count")
        per_year["term_year"] = pd.to_numeric(per_year["term_year"], errors="coerce").astype(int).astype(str)
        figure = px.bar(per_year, x="term_year", y="count", labels={"term_year":"Year", "count":"Opinions Authored"}, title=f"{name} — Opinions Authored Per Year", color_discrete_sequence=["#003057"])
        figure.update_layout(plot_bgcolor="white", xaxis={"type":"category", "tickformat":"d"}); charts["authored_year"] = json.loads(figure.to_json())
    if cases:
        vote_counts = pd.Series([str(case["vote"]).replace("_", " ").title() for case in cases]).value_counts()
        figure = px.pie(values=vote_counts.values, names=vote_counts.index, color=vote_counts.index, color_discrete_map={key.replace("_", " ").title(): value for key, value in VOTE_COLORS.items()}, title="Vote Distribution")
        charts["votes"] = json.loads(figure.to_json())
    charts["agreement"] = json.loads(agreement_heatmap(pd.DataFrame(matrix, index=JUSTICE_KEYS, columns=JUSTICE_KEYS)).to_json())
    charts["authorship"] = json.loads(authorship_bar(df).to_json())
    if not per_curiam.empty:
        frame = pd.DataFrame({"term_year":per_curiam.index, "pct":[float(n / yearly[y] * 100) for y, n in per_curiam.items()]})
        figure = px.line(frame, x="term_year", y="pct", markers=True, labels={"term_year":"Year", "pct":"% Per Curiam"}, title="Per Curiam Frequency", color_discrete_sequence=["#C8960C"])
        figure.update_layout(plot_bgcolor="white"); charts["per_curiam"] = json.loads(figure.to_json())
    return {"meta": meta, "name": name, "authored": len(authored), "participated": participation,
            "dissents": dissent, "authored_by_year": authored_by_year, "cases": cases,
            "vote_counts": [{"name": key, "count": value} for key, value in Counter(case["vote"] for case in cases).most_common()],
            "matrix_labels": [JUSTICE_DISPLAY.get(key, key) for key in JUSTICE_KEYS], "matrix": matrix, "pairs": pairs,
            "authors": authors, "per_curiam": [{"year": int(y), "percent": float(n / yearly[y] * 100)} for y, n in per_curiam.items()], "charts": charts}


@app.get("/api/assets/plotly.min.js")
def plotly_library():
    from pathlib import Path
    import plotly
    path = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    if not path.is_file():
        raise HTTPException(status_code=503, detail="Chart library unavailable")
    return FileResponse(path, media_type="application/javascript", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/analysis")
def analysis_page(year_min: int = 2000, year_max: int = 2100, rsa: str = Query(default="", max_length=100)) -> dict:
    import plotly.express as px
    from utils.charts import (outcome_bar, opinions_per_year, rsa_citation_bar, avg_decision_time_per_year,
                              avg_word_count_by_case_type, avg_word_count_by_year, avg_word_count_by_justice,
                              avg_word_count_by_year_per_justice)
    df = opinions()
    df = df[pd.to_numeric(df["term_year"], errors="coerce").between(max(2000, year_min), year_max)].copy()
    charts = {}
    def add_chart(name, figure):
        if figure.data:
            charts[name] = json.loads(figure.to_json())
    add_chart("outcomes", outcome_bar(df))
    add_chart("opinions_per_year", opinions_per_year(df))
    add_chart("decision_time", avg_decision_time_per_year(df))
    add_chart("words_by_type", avg_word_count_by_case_type(df))
    add_chart("words_by_year", avg_word_count_by_year(df))
    add_chart("words_by_justice", avg_word_count_by_justice(df))
    add_chart("words_by_justice_year", avg_word_count_by_year_per_justice(df))
    add_chart("rsa", rsa_citation_bar(df))
    topic_counts = Counter(item for value in df["topics"].dropna() for item in _list_field(value))
    if topic_counts:
        topics = pd.DataFrame([{"topic": str(k).replace("_", " ").title(), "count": v} for k, v in topic_counts.most_common(12)])
        fig = px.bar(topics, x="count", y="topic", orientation="h", color_discrete_sequence=["#003057"], title="Topic Distribution")
        fig.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
        add_chart("topics", fig)
    standards = Counter(item for value in df["standard_of_review"].dropna() for item in _list_field(value)) if "standard_of_review" in df else Counter()
    if standards:
        add_chart("standards", px.pie(names=[str(k).replace("_", " ").title() for k in standards], values=list(standards.values()), title="Standard of Review Distribution"))
    for column, key, title in (("appeal_type", "appeal_outcome", "Outcome by Appeal Type"), ("lower_court_type", "court_outcome", "Reversal Rate by Lower Court"), ("term_year", "year_outcome", "Outcome Trends Over Time")):
        grouped = df.groupby([column, "outcome"]).size().reset_index(name="count")
        if not grouped.empty:
            grouped["outcome_label"] = grouped["outcome"].map(lambda value: str(value).replace("_", " ").title())
            if column != "term_year":
                grouped[column] = grouped[column].astype(str).str.replace("_", " ").str.title()
            colors = {str(k).replace("_", " ").title(): v for k,v in OUTCOME_COLORS.items()}
            fig = (px.line(grouped, x=column, y="count", color="outcome_label", markers=True, title=title, color_discrete_map=colors) if column == "term_year" else px.bar(grouped, x=column, y="count", color="outcome_label", barmode="stack", title=title, color_discrete_map=colors))
            fig.update_layout(plot_bgcolor="white")
            add_chart(key, fig)
    divided = df[df["has_dissent"].eq(True)]  # noqa: E712
    if not divided.empty:
        counts = Counter(item for value in divided["topics"].dropna() for item in _list_field(value))
        if counts:
            top = pd.DataFrame([{"topic": str(k).replace("_", " ").title(), "count": v} for k,v in counts.most_common(10)])
            fig = px.bar(top, x="count", y="topic", orientation="h", color_discrete_sequence=["#C62828"], title="Topics in Divided Cases")
            fig.update_layout(plot_bgcolor="white", yaxis={"autorange":"reversed"})
            add_chart("divided_topics",fig)
        timeline = divided.groupby("term_year").size().reset_index(name="dissents")
        fig = px.bar(timeline, x="term_year", y="dissents", color_discrete_sequence=["#C62828"], title="Divided Decisions Per Year")
        fig.update_layout(plot_bgcolor="white")
        add_chart("divided_year",fig)
    decision_days = pd.to_numeric(df["days_to_decision"], errors="coerce")
    times = df[decision_days.ge(0)].copy()
    times["days_to_decision"] = decision_days.loc[times.index]
    mean_days = times["days_to_decision"].mean()
    rsa_df = df[df["rsa_citations"].fillna("").astype(str).str.contains(rsa.strip(), case=False, regex=False)] if rsa.strip() else df.iloc[0:0]
    def cases(frame):
        return records(frame[[col for col in ("case_name", "citation", "case_number", "date_issued", "days_to_decision", "vote_string", "outcome", "topics", "pdf_url") if col in frame]])
    return {"total": len(df), "unanimous": int(df["is_unanimous"].fillna(False).sum()), "dissents": len(divided),
            "avg_days": float(mean_days) if pd.notna(mean_days) else None, "interpretation": int(df["involves_statutory_interpretation"].fillna(False).sum()),
            "fastest": cases(times.nsmallest(5, "days_to_decision")), "slowest": cases(times.nlargest(5, "days_to_decision")),
            "divided": cases(divided), "rsa_cases": cases(rsa_df), "charts": charts, "updated": opinion_filters()["updated"]}


@app.get("/api/analysis/statute-search")
def analysis_statute_search(year_min: int = 2000, year_max: int = 2100, rsa: str = Query(default="", max_length=100)) -> dict:
    df = opinions()
    df = df[pd.to_numeric(df["term_year"], errors="coerce").between(max(2000, year_min), year_max)]
    query = rsa.strip()
    if not query:
        return {"items": []}
    matched = df[df["rsa_citations"].fillna("").astype(str).str.contains(query, case=False, regex=False)]
    columns = [c for c in ("case_name", "citation", "case_number", "date_issued", "outcome", "topics") if c in matched]
    return {"items": records(matched[columns])}


def _dispositions_in_years(year_min: int, year_max: int) -> pd.DataFrame:
    from utils.data_loader import load_argument_dispositions
    df = load_argument_dispositions()
    if df.empty:
        return df
    years = pd.to_numeric(df["term_year"], errors="coerce")
    return df[years.between(year_min, year_max)].copy()


@app.get("/api/analysis/advanced")
def advanced_analysis(year_min: int = 2000, year_max: int = 2100) -> dict:
    import plotly.express as px
    from utils.data_loader import load_argument_topics
    from utils.case_resolution import RESOLUTION_LABELS

    df = _dispositions_in_years(year_min, year_max)
    if df.empty:
        return {"count": 0}
    pretty = lambda value: str(value).replace("_", " ").title().replace("3Jx", "3JX")
    label = lambda value: pretty(RESOLUTION_LABELS.get(value, value))
    charts = {}
    def add(key, fig):
        if fig.data:
            fig.update_layout(plot_bgcolor="white")
            charts[key] = json.loads(fig.to_json())
    counts = df["resolution_type"].value_counts().rename_axis("resolution_type").reset_index(name="count")
    counts["label"] = counts["resolution_type"].map(label)
    colors = {"opinion":"#7E57C2","case_order":"#005A9C","3jx_order":"#4A7C59","multiple":"#E09F3E","needs_review":"#FFA726","unmatched":"#9E9E9E"}
    add("routing_mix", px.pie(counts, names="label", values="count", color="resolution_type", color_discrete_map=colors, hole=.3, title="Disposition Type Distribution"))
    yearly = df.groupby(["term_year", "resolution_type"]).size().reset_index(name="count")
    yearly["label"] = yearly["resolution_type"].map(label)
    add("routing_year", px.bar(yearly, x="term_year", y="count", color="label", color_discrete_map={label(k):v for k,v in colors.items()}, barmode="stack", title="Disposition Routing Trend by Year"))
    subset = df[df["resolution_type"].eq("3jx_order")]
    tables = {}
    for field,key,heading,color in (("case_type","routing_case_type","3JX Orders by Case Type","#4A7C59"),("lower_court","routing_court","3JX Orders by Lower Court","#E09F3E")):
        value_counts = subset[field].value_counts().rename_axis("name").reset_index(name="count")
        if not value_counts.empty:
            value_counts["name"] = value_counts["name"].map(pretty)
            value_counts["percent"] = value_counts["count"] / value_counts["count"].sum() * 100
            tables[key] = records(value_counts)
            fig = px.bar(value_counts,x="count",y="name",orientation="h",color_discrete_sequence=[color],text="count",title=heading)
            fig.update_layout(yaxis={"autorange":"reversed"})
            add(key,fig)
    bridge = load_argument_topics()
    selected_topics = bridge[bridge["argument_id"].isin(set(subset["argument_id"]))] if not bridge.empty else pd.DataFrame()
    if not selected_topics.empty:
        top = selected_topics["topic"].value_counts().head(15).rename_axis("name").reset_index(name="count")
        top["name"] = top["name"].map(pretty)
        tables["routing_topics"] = records(top)
        add("routing_topics",px.bar(top,x="count",y="name",orientation="h",title="Top 15 Topics in 3JX Orders",color_discrete_sequence=["#005A9C"]))
    timing = subset[subset["days_to_disposition"].notna()]
    percentile = {str(q): float(timing["days_to_disposition"].quantile(q)) for q in (0.25,0.5,0.75,0.9)} if not timing.empty else {}
    if not timing.empty:
        add("routing_timing", px.histogram(timing,x="days_to_disposition",nbins=20,title="3JX Days to Disposition Distribution",color_discrete_sequence=["#4A7C59"]))
        comparison = df[df["resolution_type"].isin(["opinion","3jx_order"]) & df["days_to_disposition"].notna()].groupby("resolution_type")["days_to_disposition"].agg(["median","count"]).reset_index()
        comparison["resolution_type"] = comparison["resolution_type"].map(label)
        tables["routing_timing"] = records(comparison)
        add("routing_timing_compare",px.bar(comparison,x="median",y="resolution_type",orientation="h",color="resolution_type",text="count",title="3JX vs Opinion: Median Days"))
    comparison = df[df["resolution_type"].isin(["opinion","3jx_order"])]
    for field,key,heading in (("case_type","compare_type","Case Type Routing: 3JX vs Opinion"),("lower_court","compare_court","Lower Court Routing: 3JX vs Opinion")):
        grouped = comparison.groupby([field,"resolution_type"]).size().reset_index(name="count")
        if not grouped.empty:
            grouped[field] = grouped[field].map(pretty)
            grouped["label"] = grouped["resolution_type"].map(label)
            add(key,px.bar(grouped,x=field,y="count",color="label",barmode="group",color_discrete_map={label(k):v for k,v in colors.items()},title=heading))
            pivot = grouped.pivot_table(index=field,columns="resolution_type",values="count",fill_value=0).reset_index()
            if "3jx_order" in pivot and "opinion" in pivot:
                pivot["3JX Rate %"] = (pivot["3jx_order"] / (pivot["3jx_order"] + pivot["opinion"]) * 100).round(1)
            tables[key] = records(pivot)
    authored = df[df["resolution_type"].eq("opinion")].copy()
    unanimous = int(authored["is_unanimous"].fillna(False).sum())
    dissents = int(authored["has_dissent"].fillna(False).sum())
    authors = authored[authored["author"].notna()].copy()
    if not authors.empty:
        authors["author"] = authors["author"].map(pretty)
        authors["outcome"] = authors["outcome"].map(lambda v: pretty(v) if pd.notna(v) else v)
        author_counts = authors["author"].value_counts().rename_axis("Author").reset_index(name="Opinions")
        tables["authors"] = records(author_counts)
        add("authors",px.bar(author_counts,x="Opinions",y="Author",orientation="h",title="Opinions Authored",color_discrete_sequence=["#7E57C2"]))
        ay = authors.groupby(["term_year","author"]).size().reset_index(name="count")
        add("authors_year",px.bar(ay,x="term_year",y="count",color="author",barmode="stack",title="Authorship by Year"))
        at = authors[authors["days_to_disposition"].notna()]
        if not at.empty:
            timing_by_author = at.groupby("author")["days_to_disposition"].agg(["median","mean","count"]).reset_index().sort_values("median",ascending=False)
            tables["author_timing"] = records(timing_by_author)
            add("author_timing",px.bar(timing_by_author,x="median",y="author",orientation="h",text="count",title="Median Days to Opinion by Author"))
            add("author_timing_box",px.box(at,x="author",y="days_to_disposition",color="author",title="Days to Opinion Distribution by Author"))
        votes = authors.groupby("author").agg(total=("author","size"),unanimous=("is_unanimous","sum"),dissent=("has_dissent","sum")).reset_index()
        votes["unanimity_rate"] = votes["unanimous"] / votes["total"] * 100
        votes["dissent_rate"] = votes["dissent"] / votes["total"] * 100
        tables["author_votes"] = records(votes.sort_values("total",ascending=False))
        add("author_unanimity",px.bar(votes,x="unanimity_rate",y="author",orientation="h",text="total",title="Unanimity Rate by Author",color_discrete_sequence=["#4A7C59"]))
        add("author_dissent",px.bar(votes,x="dissent_rate",y="author",orientation="h",text="total",title="Dissent Rate by Author",color_discrete_sequence=["#E09F3E"]))
        for field,key,heading in (("case_type","author_case_type","Authorship Heatmap: Justice × Case Type"),("outcome","author_outcome","Outcomes in Authored Opinions")):
            grouped = authors.groupby(["author",field]).size().reset_index(name="count")
            if not grouped.empty:
                pivot = grouped.pivot(index="author",columns=field,values="count").fillna(0)
                tables[key] = records(pivot.reset_index())
                add(key, px.imshow(pivot, color_continuous_scale="Blues",title=heading) if field == "case_type" else px.bar(grouped,x="author",y="count",color=field,barmode="stack",title=heading))
    return {"count": len(df), "routing_counts": {key:int(df["resolution_type"].eq(key).sum()) for key in ("opinion","case_order","3jx_order","multiple")},
            "author_count": len(authored), "unanimous": unanimous, "dissents": dissents, "percentiles": percentile, "tables": tables, "charts": charts}


@app.get("/api/analysis/advanced.csv")
def advanced_analysis_csv(kind: str = Query(pattern="^(routing|authorship)$"), year_min: int = 2000, year_max: int = 2100) -> Response:
    df = _dispositions_in_years(year_min, year_max)
    if df.empty:
        raise HTTPException(status_code=404, detail="No disposition data")
    if kind == "authorship":
        df = df[df["resolution_type"].eq("opinion") & df["author"].notna()].copy()
        for col in ("author", "outcome"):
            df[col] = df[col].map(lambda v: str(v).replace("_", " ").title() if pd.notna(v) else v)
        columns = ["argument_id","case_name","argument_date","disposition_date","days_to_disposition","author","is_unanimous","has_dissent","outcome","case_type","vote_string"]
        filename = f"justice_authorship_{year_min}_{year_max}.csv"
    else:
        columns = ["argument_id","case_name","argument_date","term_year","resolution_type","disposition_date","days_to_disposition","case_type","lower_court","outcome"]
        filename = f"3jx_routing_{year_min}_{year_max}.csv"
    return Response(df[columns].to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _filter_dispositions(df, resolution, case_type, outcome, age):
    for field, value in (("resolution_type", resolution), ("case_type", case_type), ("outcome", outcome)):
        if value:
            df = df[df[field].eq(value)]
    days = df["days_to_disposition"]
    if age == "0-90":
        df = df[days.between(0,90)]
    elif age == "91-180":
        df = df[(days > 90) & (days <= 180)]
    elif age == "181-365":
        df = df[(days > 180) & (days <= 365)]
    elif age == "365+":
        df = df[days > 365]
    elif age == "pending":
        df = df[days.isna()]
    return df


@app.get("/api/analysis/arguments")
def analysis_arguments(year_min: int = 2000, year_max: int = 2100, resolution: str = "", case_type: str = "", outcome: str = "",
                       age: str = Query(default="", pattern=r"^(|0-90|91-180|181-365|365\+|pending)$")) -> dict:
    import plotly.express as px
    from utils.case_resolution import RESOLUTION_LABELS
    from utils.data_loader import load_argument_dispositions_metadata
    base = _dispositions_in_years(year_min,year_max)
    if base.empty:
        return {"available": False}
    facets = {col: sorted(str(value) for value in base[col].dropna().unique() if str(value) and (col != "outcome" or value != "issued")) for col in ("resolution_type","case_type","outcome")}
    df = _filter_dispositions(base,resolution,case_type,outcome,age)
    resolved = df[df["resolution_type"].isin(["opinion","case_order","3jx_order","multiple"])]
    timing = resolved[resolved["days_to_disposition"].notna() & (resolved["days_to_disposition"] >= 0)]
    chart = {}
    def add(key, figure):
        if figure.data:
            figure.update_layout(plot_bgcolor="white")
            chart[key] = json.loads(figure.to_json())
    labels = lambda value: str(RESOLUTION_LABELS.get(value,value)).replace("_"," ").title().replace("3Jx","3JX")
    colors = {"opinion":"#7E57C2","case_order":"#005A9C","3jx_order":"#4A7C59","multiple":"#E09F3E","needs_review":"#FFA726","unmatched":"#9E9E9E"}
    counts = df["resolution_type"].value_counts().rename_axis("resolution_type").reset_index(name="count")
    if not counts.empty:
        counts["label"] = counts["resolution_type"].map(labels)
        add("mix",px.bar(counts,x="label",y="count",color="resolution_type",color_discrete_map=colors,title="Arguments by Disposition Type"))
    yearly = df.groupby(["term_year","resolution_type"]).size().reset_index(name="count")
    if not yearly.empty:
        yearly["label"] = yearly["resolution_type"].map(labels)
        add("yearly",px.bar(yearly,x="term_year",y="count",color="label",color_discrete_map={labels(k):v for k,v in colors.items()},barmode="stack",title="Disposition Mix by Year"))
    if not timing.empty:
        add("timing_hist",px.histogram(timing,x="days_to_disposition",nbins=30,range_x=[0,max(1,float(timing["days_to_disposition"].max()))],title="Distribution of Days to Disposition",color_discrete_sequence=["#005A9C"]))
        for field,key,title,color in (("resolution_type","timing_type","Median Days by Disposition Type","#005A9C"),("case_type","timing_case","Median Days to Disposition by Case Type","#7E57C2"),("outcome","timing_outcome","Median Days to Disposition by Outcome","#4A7C59")):
            if (field == "case_type" and case_type) or (field == "outcome" and outcome):
                continue
            group = timing.groupby(field)["days_to_disposition"].agg(["median","count"]).reset_index().sort_values("median",ascending=False)
            if group.empty:
                continue
            group["label"] = group[field].map(labels if field == "resolution_type" else lambda value: str(value).replace("_"," ").title())
            figure = px.bar(group,x="median",y="label",orientation="h",text="count",title=title,color_discrete_sequence=[color])
            figure.update_traces(texttemplate="n=%{text}",textposition="outside")
            figure.update_layout(yaxis={"autorange":"reversed"})
            add(key,figure)
    columns = ["case_name","case_number","days_to_disposition","resolution_type","argument_date","disposition_date"]
    percentiles = {str(q):float(timing["days_to_disposition"].quantile(q)) for q in (0.1,0.25,0.5,0.75,0.9)} if not timing.empty else {}
    median = resolved["days_to_disposition"].median()
    return {"available": True,"facets":facets,"total":len(df),"resolved":len(resolved),"median":float(median) if pd.notna(median) else None,
            "transcripts":int(df["has_transcript"].fillna(False).sum()),"combined":int(df["is_combined_docket"].fillna(False).sum()),
            "mean":float(timing["days_to_disposition"].mean()) if not timing.empty else None,"percentiles":percentiles,
            "fastest":records(timing.nsmallest(10,"days_to_disposition")[columns]),"slowest":records(timing.nlargest(10,"days_to_disposition")[columns]),
            "charts":chart,"metadata":load_argument_dispositions_metadata()}


@app.get("/api/analysis/arguments.csv")
def analysis_arguments_csv(year_min: int = 2000, year_max: int = 2100, resolution: str = "", case_type: str = "", outcome: str = "",
                           age: str = Query(default="", pattern=r"^(|0-90|91-180|181-365|365\+|pending)$")) -> Response:
    df = _dispositions_in_years(year_min,year_max)
    if df.empty:
        raise HTTPException(status_code=404, detail="No disposition data")
    df = _filter_dispositions(df,resolution,case_type,outcome,age)
    columns = ["argument_id","case_name","argument_date","term_year","resolution_type","disposition_date","days_to_disposition","outcome","case_type","author","is_unanimous","has_dissent","lower_court","duration_seconds","has_transcript"]
    return Response(df[columns].to_csv(index=False),media_type="text/csv",headers={"Content-Disposition":'attachment; filename="argument_dispositions_filtered.csv"'})


@app.get("/api/analysis/argument-matches")
def argument_matches(year_min: int = 2000, year_max: int = 2100) -> dict:
    import plotly.express as px
    from utils.case_resolution import RESOLUTION_LABELS, argument_resolution_summary, disposition_source_summary
    from utils.data_loader import load_brief_counsel, load_docket_crosswalk
    from utils.dockets import apply_docket_crosswalk
    arguments = argument_records()
    case_orders = orders()
    df = opinions()
    df = df[pd.to_numeric(df["term_year"],errors="coerce") >= 2000]
    crosswalk = load_docket_crosswalk()
    disposition_orders = pd.concat([apply_docket_crosswalk(case_orders[case_orders["order_source"] == kind],crosswalk,kind) for kind in ("case_order","3jx_order")],ignore_index=True)
    disposition_opinions = apply_docket_crosswalk(df,crosswalk,"opinion")
    filtered = [row for row in arguments if year_min <= pd.to_numeric(row.get("term_year"),errors="coerce") <= year_max]
    resolutions = argument_resolution_summary(filtered,disposition_orders,disposition_opinions)
    summary = disposition_source_summary(arguments,load_brief_counsel(),disposition_orders,disposition_opinions)
    charts = {}
    resolved = 0
    if not resolutions.empty:
        resolved = int(resolutions["resolution"].isin(["case_order","3jx_order","opinion","multiple"]).sum())
        counts = resolutions["resolution"].value_counts().rename_axis("resolution").reset_index(name="count")
        counts["label"] = counts["resolution"].map(RESOLUTION_LABELS)
        fig = px.bar(counts,x="label",y="count",color="resolution",title="Disposition for Recorded Oral Arguments",color_discrete_map={"case_order":"#005A9C","3jx_order":"#4A7C59","opinion":"#7E57C2","multiple":"#E09F3E","needs_review":"#E09F3E","unmatched":"#9E9E9E"})
        fig.update_layout(plot_bgcolor="white",showlegend=False)
        charts["resolutions"] = json.loads(fig.to_json())
    if not summary.empty:
        melted = summary.melt(id_vars="Disposition",var_name="Participation",value_name="Dockets")
        fig = px.bar(melted,x="Disposition",y="Dockets",color="Participation",barmode="group",title="Published Dispositions Linked by Docket",color_discrete_sequence=["#005A9C","#E09F3E"])
        fig.update_layout(plot_bgcolor="white")
        charts["sources"] = json.loads(fig.to_json())
    return {"arguments":len(resolutions),"matched":resolved,"sources":records(summary),"charts":charts}


@app.post("/api/legal/semantic-search")
def legal_semantic_search(request: LegalSearchRequest) -> dict:
    from utils.semantic_search import semantic_search
    query = request.query.strip()
    if len(query) < 3:
        raise HTTPException(status_code=422, detail="Enter at least three characters")
    try:
        results = semantic_search(query, request.limit)
    except Exception as exc:
        logger.exception("Semantic search failed")
        raise HTTPException(status_code=503, detail="Semantic search is unavailable") from exc
    df = opinions()
    for result in results:
        key = str(result.get("docket_number") or result.get("href") or result.get("case_number") or "")
        matched = df[df["case_number"].astype(str) == key]
        if not matched.empty:
            row = records(matched.iloc[:1])[0]
            result.update({"case_name": row.get("case_name"), "summary": row.get("summary_paragraph"), "pdf_url": row.get("pdf_url")})
    return {"results": results}


@app.get("/api/legal/authority/{case_number}")
def legal_authority(case_number: str, as_of: date) -> dict:
    from utils.authority_graph import controlling_treatments, load_treatments
    from utils.case_recommender import get_similar_cases
    from utils.citation_network import landmark_cases, render_citation_graph
    if not re.fullmatch(r"[A-Za-z0-9_-]+", case_number):
        raise HTTPException(status_code=400, detail="Invalid case number")
    if not opinions()["case_number"].astype(str).eq(case_number).any():
        raise HTTPException(status_code=404, detail="Opinion not found")
    treatments = controlling_treatments(load_treatments(data_root() / "processed" / "authority_treatments.json"),case_number,as_of)
    treatment_rows = [{**asdict(item),"display_label":item.display_label} for item in treatments[:30]]
    similar = get_similar_cases(case_number,opinions(),top_k=5)
    graph = {}
    for source, rec in _optional_json("citations.json",{}).items():
        graph[source] = [str(item.get("resolved_case_number")) if isinstance(item,dict) else str(item) for item in rec.get("cites",[]) if (item.get("resolved_case_number") if isinstance(item,dict) else item)]
    fig = json.loads(render_citation_graph(graph,focus_case=case_number).to_json()) if any(graph.values()) else None
    return {"treatments": treatment_rows,"similar": records(similar),"graph":fig,"landmarks":records(landmark_cases(graph,top_n=20)) if any(graph.values()) else []}


@app.get("/api/legal/issues")
def legal_issues(as_of: date) -> dict:
    from utils.authority_graph import load_treatments
    from utils.issue_lifecycle import build_issue_threads, proposition_cards, holding_diff, stable_issue_url
    threads = build_issue_threads(opinions(),load_treatments(data_root() / "processed" / "authority_treatments.json"),as_of=as_of,min_cases=3)
    output = []
    for thread in threads:
        cards = proposition_cards(thread)
        states = [asdict(state) for state in thread.states]
        output.append({"id":thread.issue_id,"title":thread.title,"proposition":thread.proposition,"unresolved_split":thread.unresolved_split,
                       "states":states,"majority":asdict(cards["majority"]) if cards["majority"] else None,"divided":asdict(cards["divided"]) if cards["divided"] else None,
                       "diff":holding_diff(thread.states[-2].rule_text,thread.states[-1].rule_text) if len(thread.states) >= 2 else "",
                       "url":stable_issue_url(thread.issue_id,as_of)})
    return {"issues":output}


def _public_release_manifest() -> dict:
    from utils.data_releases import load_latest_manifest

    root = data_root()
    runtime_manifest_path = root.parent / "manifest.json"
    if runtime_manifest_path.is_file():
        try:
            runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
            public_manifest = runtime_manifest.get("public_data_manifest")
            if isinstance(public_manifest, dict) and public_manifest:
                return public_manifest
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    # Local development builds the public snapshot under data/releases. Keep
    # the prior repository-root location as a compatibility fallback.
    for releases_root in (root / "releases", root.parent / "releases"):
        try:
            manifest = load_latest_manifest(releases_root)
            if manifest:
                return manifest
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError):
            continue
    return {}


@app.get("/api/legal/workspace/version")
def workspace_version() -> dict:
    manifest = _public_release_manifest()
    version = manifest.get("content_sha256") or f"working-corpus-{len(opinions())}-{opinion_filters()['updated']}"
    return {"corpus_version":str(version)}


@app.get("/api/legal/workspace/item/{case_number}")
def workspace_case_item(case_number: str) -> dict:
    data = get_opinion(case_number)
    text, row = data["text"], data["opinion"]
    summary = str(row.get("summary_paragraph") or "")
    return {"case_id":case_number,"kind":"holding","start":0,"end":min(len(text),max(300,len(summary))) if text else 0,"source_url":str(row.get("pdf_url") or "")}


@app.post("/api/legal/workspace/export")
def export_research_workspace(workspace: WorkspacePayload, format: str = Query(pattern="^(pdf|markdown|json)$")) -> Response:
    from html import escape
    from utils.research_workspace import resolve_workspace, export_packet_json, export_packet_markdown, export_packet_pdf
    payload = workspace.model_dump(exclude_none=True)
    if payload["schema_version"] != 1 or any(item["end"] < item["start"] for item in payload["items"]):
        raise HTTPException(status_code=422,detail="Invalid workspace")
    def resolver(case_id):
        try:
            result = get_opinion(case_id)
        except HTTPException:
            return None
        return {**result["opinion"],"text":result["text"]}
    try:
        resolved = resolve_workspace(payload,resolver)
        if format == "pdf":
            # ReportLab interprets paragraph markup. Escape data fields while
            # leaving source_span to the exporter, which already escapes it.
            safe = {**resolved,"corpus_version":escape(str(resolved["corpus_version"])),
                    "items":[{**item,**{key:escape(str(item.get(key) or "")) for key in ("case_name","citation","case_id","source_url","pinpoint")}} for item in resolved["items"]],
                    "notes":[{**note,"text":escape(str(note.get("text") or ""))} for note in resolved["notes"]]}
            content, media, extension = export_packet_pdf(safe), "application/pdf", "pdf"
        elif format == "markdown":
            content, media, extension = export_packet_markdown(resolved), "text/markdown", "md"
        else:
            content, media, extension = export_packet_json(resolved), "application/json", "json"
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid workspace") from exc
    return Response(content,media_type=media,headers={"Content-Disposition":f'attachment; filename="nh_research_packet.{extension}"'})


@app.get("/api/legal/transcript-moments")
def transcript_moments(q: str = Query(default="",max_length=300), case_number: str = Query(default="",max_length=100)) -> dict:
    from utils.transcript_search import search_transcript_corpus
    if case_number and not re.fullmatch(r"[A-Za-z0-9_-]+",case_number):
        raise HTTPException(status_code=400,detail="Invalid docket")
    frame = search_transcript_corpus(q,transcripts_dir=data_root() / "processed" / "oral_arguments",case_filter=case_number or None,limit=100)
    return {"items":records(frame)}


@app.get("/api/legal/court-calendar")
def court_calendar() -> dict:
    from utils.court_calendar import fetch_oral_argument_schedule
    try:
        return {"items":records(fetch_oral_argument_schedule())}
    except Exception as exc:
        logger.exception("Court schedule unavailable")
        raise HTTPException(status_code=503,detail="The official schedule could not be fetched") from exc


@app.get("/api/legal/date-calculator")
def date_calculator(start: date, days: int = Query(default=30,ge=0,le=365), business: bool = False) -> dict:
    from utils.court_calendar import compute_filing_deadline
    return {"date":compute_filing_deadline(start,days,business_days=business)}


@app.get("/api/legal/timeline/{case_number}")
def legal_case_timeline(case_number: str) -> dict:
    import plotly.express as px
    from utils.roadmap_analytics import build_case_timeline
    get_opinion(case_number)
    frame = build_case_timeline(case_number,opinions(),orders(),_optional_json("oral_arguments.json",[]))
    chart = None
    if not frame.empty:
        fig = px.scatter(frame,x="event_date",y="court",color="event_type",hover_name="description",title="Case proceeding timeline")
        fig.update_traces(marker_size=13)
        chart = json.loads(fig.to_json())
    return {"items":records(frame),"chart":chart}


@app.get("/api/legal/viewer/{case_number}")
def legal_opinion_viewer(case_number: str) -> dict:
    from utils.opinion_viewer import extract_key_passages
    from utils.readability import compute_readability
    from utils.roadmap_analytics import tag_bar_exam_relevance
    from utils.legal_glossary import find_terms
    data = get_opinion(case_number)
    row,text = data["opinion"],data["text"]
    summary = str(row.get("summary_paragraph") or "")
    return {"opinion":row,"scores":compute_readability(text),"bar_tags":tag_bar_exam_relevance(f"{summary} {text[:5000]}",row.get("topics")),
            "terms":find_terms(summary),"highlights":extract_key_passages(text,summary=summary)}


class PredictionRequest(BaseModel):
    topic: str = Field(max_length=100)
    appellant_type: str = Field(pattern="^(Individual|Business|Government|Other)$")
    lower_court_type: str = Field(max_length=150)
    year: int = Field(ge=2002,le=2035)
    word_count: int = Field(ge=0,le=50000)
    criminal: bool = False
    administrative: bool = False


class LabelRequest(BaseModel):
    text: str = Field(max_length=50000)


@app.get("/api/legal/analytics/options")
def legal_analytics_options() -> dict:
    df = opinions()
    topics = sorted({str(item) for value in df["topics"].dropna() for item in _list_field(value)})
    return {"topics":topics,"courts":sorted(df["lower_court_type"].dropna().astype(str).unique().tolist()),
            "authors":sorted(df["author_display"].dropna().astype(str).unique().tolist())}


@app.post("/api/legal/analytics/predict")
def legal_predict(request: PredictionRequest) -> dict:
    from utils.ml_predictor import predict_outcome
    details = {"topic":request.topic,"appellant_type":request.appellant_type,"author":"unknown","lower_court_type":request.lower_court_type,
               "year":request.year,"term_month":1,"word_count":request.word_count,"num_prior_cases_cited":0,
               "is_criminal_appeal":int(request.criminal),"is_administrative_appeal":int(request.administrative),"panel_size":5}
    try:
        return asdict(predict_outcome(details,opinions=opinions(),model_path=data_root() / "processed" / "outcome_model.joblib"))
    except Exception as exc:
        logger.exception("Outcome model failed")
        raise HTTPException(status_code=503,detail="Outcome model could not run") from exc


@app.post("/api/legal/analytics/topic-labels")
def legal_topic_labels(request: LabelRequest) -> dict:
    from utils.topic_labeler import label_with_confidence
    return {"labels":label_with_confidence(request.text)}


@lru_cache(maxsize=2)
def _attorney_outcomes_cached(root: str, opinions_mtime: int, counsel_mtime: int):
    from utils.roadmap_analytics import attorney_win_rates
    del root, opinions_mtime, counsel_mtime
    facts = _optional_json("case_counsel.json",{}).get("facts",[])
    return attorney_win_rates(opinions(),facts)


def _attorney_outcomes():
    root = data_root()
    source = root / "processed" / "opinions.csv"
    counsel = root / "processed" / "case_counsel.json"
    return _attorney_outcomes_cached(str(root),source.stat().st_mtime_ns if source.is_file() else 0,counsel.stat().st_mtime_ns if counsel.is_file() else 0)


@app.get("/api/legal/analytics/attorneys")
def legal_attorneys() -> dict:
    frame = _attorney_outcomes()
    if frame.empty:
        return {"items":[]}
    counts = frame.groupby("attorney")["docket"].nunique().sort_values(ascending=False)
    return {"items":[{"name":str(name),"count":int(count)} for name,count in counts.items()]}


@app.get("/api/legal/analytics/attorneys/detail")
def legal_attorney_detail(attorney: str = Query(min_length=1,max_length=300)) -> dict:
    import plotly.express as px
    from utils.roadmap_analytics import summarize_attorney
    frame = _attorney_outcomes()
    if frame.empty or not frame["attorney"].eq(attorney).any():
        raise HTTPException(status_code=404,detail="Attorney not found")
    summary = summarize_attorney(frame,attorney)
    figures = {}
    for key,field,title in (("by_topic","topic","Win rate by topic"),("by_author","author","Win rate by opinion author"),("over_time","year","Win rate over time")):
        if not summary[key].empty:
            figures[key] = json.loads(px.bar(summary[key],x=field,y="mean",color="count",title=title,labels={"mean":"Win rate"}).to_json())
    return {"total_cases":summary["total_cases"],"win_rate":summary["win_rate"],"unique_topics":summary["unique_topics"],"charts":figures}


@app.get("/api/legal/analytics/justice-topics")
def legal_justice_topics(minimum: int = Query(default=5,ge=1,le=25)) -> dict:
    import plotly.express as px
    from utils.roadmap_analytics import justice_topic_voting
    frame = justice_topic_voting(_optional_json("all_opinions.json",[]))
    if frame.empty:
        return {"chart":None,"has_votes":False}
    aggregate = frame.groupby(["justice","topic"])["pro_appellant"].agg(["mean","count"]).reset_index()
    aggregate = aggregate[aggregate["count"] >= minimum]
    if aggregate.empty:
        return {"chart":None,"has_votes":True}
    pivot = aggregate.pivot(index="justice",columns="topic",values="mean")
    return {"chart":json.loads(px.imshow(pivot,color_continuous_scale="RdYlGn",zmin=0,zmax=1,title="Observed pro-appellant disposition rate",aspect="auto").to_json()),"has_votes":True}


@app.get("/api/legal/analytics/trends")
def legal_analytics_trends(topic: str = Query(default="",max_length=100), author: str = Query(default="",max_length=200)) -> dict:
    import plotly.express as px
    from utils.roadmap_analytics import disposition_trends
    df = opinions()
    trend = disposition_trends(df,topic or None)
    figure = json.loads(px.line(trend,x="year",y="mean",markers=True,title="Annual observed affirmance rate",labels={"mean":"Affirmance rate","year":"Year"}).to_json()) if not trend.empty else None
    authored = df[df["author_display"].astype(str).eq(author)].copy() if author else df.iloc[0:0]
    if authored.empty:
        return {"trend":figure,"profile":None}
    affirmed = authored["outcome"].fillna("").astype(str).str.lower().isin({"affirmed","affirmed_in_part"})
    words = pd.to_numeric(authored["word_count"],errors="coerce").mean()
    topic_rows = [{"Topic":name,"Affirmed":int(won)} for (_,row),won in zip(authored.iterrows(),affirmed) for name in _list_field(row.get("topics"))]
    topic_stats = pd.DataFrame(topic_rows).groupby("Topic")["Affirmed"].agg(Opinions="count",Affirmance_rate="mean").reset_index().sort_values(["Opinions","Topic"],ascending=[False,True]).head(15) if topic_rows else pd.DataFrame()
    words_list = [word.strip(".,;:()[]") for word in authored["summary_paragraph"].fillna("").str.cat(sep=" ").lower().split() if len(word.strip(".,;:()[]"))>7]
    return {"trend":figure,"profile":{"count":len(authored),"affirmance_rate":float(affirmed.mean()),"average_words":float(words) if pd.notna(words) else None,
                    "topics":records(topic_stats),"frequent_words":[word for word,_ in Counter(words_list).most_common(12)]}}


@app.get("/api/legal/analytics/questions")
def legal_question_examples(author: str = Query(min_length=1,max_length=200)) -> dict:
    from utils.transcript_search import timestamp_url
    df = opinions()
    case_ids = df.loc[df["author_display"].astype(str).eq(author),"case_number"].astype(str).tolist()
    output = []
    for case_id in case_ids:
        if not re.fullmatch(r"[A-Za-z0-9_-]+",case_id):
            continue
        path = data_root() / "processed" / "oral_arguments" / f"{case_id}.json"
        if not path.is_file():
            continue
        try:
            source = json.loads(path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):
            continue
        for segment in source.get("segments",[]):
            text = str(segment.get("text") or "").strip()
            if segment.get("display_speaker") != "Justice" or ("?" not in text and not re.match(r"^(?:what|why|how|when|where|who|which|could|would|do|does|did|is|are|can)\b",text,re.IGNORECASE)):
                continue
            start = float(segment.get("start") or 0)
            output.append({"docket":case_id,"start_sec":start,"question":text,"timestamp_url":timestamp_url(str(source.get("vimeo_url") or ""),start)})
            if len(output) >= 12:
                return {"items":output}
    return {"items":output}


@app.get("/api/legal/open-data")
def legal_open_data() -> dict:
    from utils.legal_glossary import NH_LEGAL_GLOSSARY
    manifest = _public_release_manifest()
    return {"opinion_count":len(opinions()),"manifest":manifest,
            "glossary":[{"Term":term,"Definition":definition} for term,definition in NH_LEGAL_GLOSSARY.items()]}


@app.get("/api/legal/open-data/opinions.{format}")
def legal_bulk_export(format: str) -> Response:
    frame = opinions().drop(columns=["opinion_text"],errors="ignore")
    if format == "csv":
        content,media = frame.to_csv(index=False),"text/csv"
    elif format == "json":
        content,media = frame.to_json(orient="records",date_format="iso"),"application/json"
    else:
        raise HTTPException(status_code=404,detail="Unsupported format")
    return Response(content,media_type=media,headers={"Content-Disposition":f'attachment; filename="nh_supreme_court_opinions.{format}"'})


@app.get("/api/legal/open-data/digest")
def legal_digest(download: bool = False) -> Response:
    from utils.weekly_digest import build_weekly_digest_html
    headers = {"Content-Disposition":'attachment; filename="granite_state_appeals_weekly_digest.html"'} if download else {"Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'; sandbox"}
    return Response(build_weekly_digest_html(opinions()),media_type="text/html",headers=headers)


def _quality_queue() -> pd.DataFrame:
    from utils.provenance import load_observations, observation_from_record, rank_review_queue
    frame = load_observations(data_root() / "processed" / "field_observations.sqlite")
    if frame.empty:
        frame = pd.DataFrame([asdict(observation_from_record(record,field)) for record in _optional_json("all_opinions.json",[])[:250] for field in ("date_issued","outcome","author","topics","votes","summary_paragraph")])
    return rank_review_queue(frame)


@app.get("/api/legal/open-data/quality")
def legal_quality() -> dict:
    from utils.evaluation_gates import DEFAULT_THRESHOLDS,gate_release
    queue = _quality_queue().head(100)
    columns = ["record_id","field_name","confidence","downstream_impact","review_priority","method","extractor_version","source_sha256"]
    smoke = gate_release({"citation_precision":1.0,"answer_coverage":1.0,"unsupported_claim_rate":0.0,"temporal_leakage_rate":0.0})
    return {"queue":records(queue[columns]) if not queue.empty else [],"review_enabled":bool(os.environ.get("NHSC_REVIEW_TOKEN") and os.environ.get("NHSC_REVIEW_DB")),
            "smoke_passed":smoke.passed,"thresholds":DEFAULT_THRESHOLDS}


class ReviewRequest(BaseModel):
    record_id: str = Field(min_length=1,max_length=100)
    field_name: str = Field(min_length=1,max_length=100)
    source_sha256: str = Field(min_length=1,max_length=128)
    extractor_version: str = Field(min_length=1,max_length=100)
    reviewed_value: str = Field(min_length=1,max_length=20000)


@app.post("/api/legal/open-data/review")
def save_legal_review(request: ReviewRequest, x_review_token: str = Header(default="",max_length=512)) -> dict:
    import sqlite3
    from datetime import timezone
    token, db = os.environ.get("NHSC_REVIEW_TOKEN", ""), os.environ.get("NHSC_REVIEW_DB", "")
    if not token or not db:
        raise HTTPException(status_code=503,detail="Reviewed corrections are not configured")
    if not hmac.compare_digest(token,x_review_token):
        raise HTTPException(status_code=403,detail="Review access denied")
    queue = _quality_queue().head(100)
    match = queue[(queue["record_id"].astype(str)==request.record_id) & (queue["field_name"].astype(str)==request.field_name) & (queue["source_sha256"].astype(str)==request.source_sha256) & (queue["extractor_version"].astype(str)==request.extractor_version)]
    if match.empty:
        raise HTTPException(status_code=404,detail="Observation not found in the review queue")
    try:
        value = json.loads(request.reviewed_value)
    except json.JSONDecodeError:
        value = request.reviewed_value.strip()
    if not request.reviewed_value.strip():
        raise HTTPException(status_code=422,detail="Enter the reviewed value")
    # Corrections are stored separately from immutable runtime releases.
    with sqlite3.connect(db) as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS reviewed_observation (record_id TEXT NOT NULL, field_name TEXT NOT NULL, source_sha256 TEXT NOT NULL, extractor_version TEXT NOT NULL, reviewed_value_json TEXT NOT NULL, reviewed_at TEXT NOT NULL, PRIMARY KEY(record_id,field_name,source_sha256,extractor_version))""")
        connection.execute("""INSERT INTO reviewed_observation VALUES (?,?,?,?,?,?) ON CONFLICT(record_id,field_name,source_sha256,extractor_version) DO UPDATE SET reviewed_value_json=excluded.reviewed_value_json,reviewed_at=excluded.reviewed_at""",(request.record_id,request.field_name,request.source_sha256,request.extractor_version,json.dumps(value,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
    return {"status":"saved"}


@app.get("/api/arguments/people")
def oral_argument_people() -> dict:
    from utils.data_loader import load_firm_metadata
    payload = _optional_json("oral_arguments_attorney_stats.json",{})
    return {"attorneys":payload.get("attorney_stats",[]),"firms":payload.get("firm_stats",[]),"firm_metadata":load_firm_metadata().get("lookup",{})}


@app.get("/api/arguments/people/visualizations")
def oral_argument_people_visualizations() -> dict:
    import plotly.express as px
    data = oral_argument_people()
    attorneys, firms = data["attorneys"], data["firms"]
    by_name = {row["attorney_name"]: row for row in attorneys}
    hierarchy = [{"Firm":firm["firm_name"], "Attorney":name, "Arguments":by_name[name]["total_arguments"]}
                 for firm in firms[:20] for name in firm.get("attorneys", []) if name in by_name]
    scatter = [{"Attorney":a["attorney_name"], "Firm":a.get("firm") or "Unknown", "Arguments":a["total_arguments"],
                "Total Hours":a["total_duration_hours"], "Avg Minutes":a.get("average_duration_minutes", 0)}
               for a in attorneys if a.get("total_duration_hours", 0) > 0]
    treemap = [{"Firm":f["firm_name"], "Arguments":f["total_arguments"], "Attorneys":f["unique_attorneys"], "Hours":f.get("total_duration_hours", 0)} for f in firms[:15]]
    charts = {}
    if hierarchy:
        fig = px.sunburst(pd.DataFrame(hierarchy), path=["Firm", "Attorney"], values="Arguments", title="Top 20 Firms: Attorney Distribution by Arguments", color="Arguments", color_continuous_scale="Blues")
        fig.update_layout(height=700); charts["hierarchy"] = json.loads(fig.to_json())
    if scatter:
        fig = px.scatter(pd.DataFrame(scatter), x="Arguments", y="Total Hours", size="Avg Minutes", color="Firm", hover_data=["Attorney"], title="Attorney Arguments vs Total Time (bubble size = avg duration)", labels={"Total Hours":"Total Argument Time (hours)", "Arguments":"Number of Arguments"})
        fig.update_layout(plot_bgcolor="white", height=600); charts["scatter"] = json.loads(fig.to_json())
    if treemap:
        fig = px.treemap(pd.DataFrame(treemap), path=["Firm"], values="Arguments", color="Hours", hover_data=["Attorneys"], title="Top 15 Firms: Arguments and Time Breakdown", color_continuous_scale="Reds")
        fig.update_layout(height=600); charts["treemap"] = json.loads(fig.to_json())
    return {"charts":charts}


@app.get("/api/arguments/people/interactions")
def oral_argument_interactions(justice: str = Query(default="", max_length=200)) -> dict:
    import plotly.express as px
    from utils.data_loader import load_attorney_justice_interactions
    data = load_attorney_justice_interactions()
    attorneys, justices = data.get("attorney_interactions", []), data.get("justice_interactions", [])
    if not attorneys:
        return {"available":False, "charts":{}, "justices":[], "summary":data.get("summary", {})}
    names = [row["justice"] for row in justices]
    chosen = next((row for row in justices if row["justice"] == justice), justices[0] if justices else None)
    charts = {}
    def add(key, figure, *, horizontal=False):
        figure.update_layout(plot_bgcolor="white", **({"yaxis":{"categoryorder":"total ascending"}} if horizontal else {}))
        charts[key] = json.loads(figure.to_json())
    if chosen and chosen.get("top_attorneys"):
        frame = pd.DataFrame(chosen["top_attorneys"][:20])
        add("attorneys", px.bar(frame, x="arguments", y="attorney", orientation="h", title=f"Top 20 Attorneys Before {chosen['justice']}", labels={"arguments":"Arguments", "attorney":"Attorney"}, color="arguments", color_continuous_scale="Blues"), horizontal=True)
    if justices:
        frame = pd.DataFrame(justices).rename(columns={"justice":"Justice", "total_arguments":"Arguments", "unique_attorneys":"Attorneys"})
        add("workload", px.bar(frame, x="Arguments", y="Justice", orientation="h", title="Arguments Heard by Justice (2015-2026)", color="Arguments", color_continuous_scale="Reds"), horizontal=True)
        add("unique", px.bar(frame, x="Attorneys", y="Justice", orientation="h", title="Unique Attorneys per Justice", color="Attorneys", color_continuous_scale="Greens"), horizontal=True)
    rows = [{"Attorney":a["attorney_name"], "Justice":item["justice"], "Arguments":item["arguments"]} for a in attorneys[:20] for item in a.get("interactions", [])]
    if rows:
        pivot = pd.DataFrame(rows).pivot(index="Attorney", columns="Justice", values="Arguments").fillna(0)
        figure = px.imshow(pivot, labels={"x":"Justice", "y":"Attorney", "color":"Arguments"}, title="Attorney-Justice Interaction Heatmap (Top 20 Attorneys)", color_continuous_scale="YlOrRd", aspect="auto")
        figure.update_layout(height=700); add("heatmap", figure)
    return {"available":True, "summary":data.get("summary", {}), "justices":names, "selected":chosen, "charts":charts}


@app.get("/api/arguments/people.csv")
def oral_argument_people_csv(kind: str = Query(pattern="^(attorneys|firms)$")) -> Response:
    data = oral_argument_people()
    if kind == "attorneys":
        columns = ["attorney_name","firm","total_arguments","total_duration_hours","average_duration_minutes","first_argument_date","last_argument_date"]
        filename = "nh_attorneys_stats.csv"
    else:
        columns = ["firm_name","total_arguments","unique_attorneys","total_duration_hours","average_duration_minutes","first_argument_date","last_argument_date"]
        filename = "nh_firms_stats.csv"
    df = pd.DataFrame(data[kind])
    return Response(df[[col for col in columns if col in df.columns]].to_csv(index=False),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="{filename}"'})


@app.get("/api/arguments/profile")
def oral_argument_profile(kind: str = Query(pattern="^(attorney|firm)$"), name: str = Query(min_length=1,max_length=300)) -> dict:
    from utils.data_loader import load_argument_dispositions, load_argument_participants, load_argument_topics
    data = oral_argument_people()
    key = "attorney_name" if kind == "attorney" else "firm_name"
    profile = next((row for row in data["attorneys" if kind == "attorney" else "firms"] if row.get(key) == name),None)
    if profile is None:
        raise HTTPException(status_code=404,detail="Profile not found")
    args = {str(row.get("case_number")):row for row in argument_records()}
    cases = [{k:v for k,v in args[str(docket)].items() if k != "transcript_text"} for docket in profile.get("cases",[]) if str(docket) in args]
    if kind == "firm":
        case_attorneys = _optional_json("oral_arguments_attorney_stats.json", {}).get("case_attorneys", {})
        for row in cases:
            roster = case_attorneys.get(str(row.get("case_number")), [])
            row["firm_attorneys"] = ", ".join(a.get("name", "") for a in roster if a.get("firm") == name and a.get("name"))
    cases.sort(key=lambda row:str(row.get("argument_date") or ""),reverse=True)
    dispositions, participants, topics = load_argument_dispositions(),load_argument_participants(),load_argument_topics()
    matched = pd.DataFrame()
    if not participants.empty and not dispositions.empty:
        column = "attorney_name" if kind == "attorney" else "firm"
        ids = set(participants.loc[participants[column].eq(name),"argument_id"])
        matched = dispositions[dispositions["argument_id"].isin(ids)]
    else:
        ids = set()
    resolution = None
    if not matched.empty:
        resolved = matched[matched["resolution_type"].isin(["opinion","case_order","3jx_order","multiple"])]
        days = pd.to_numeric(resolved["days_to_disposition"],errors="coerce").dropna()
        count = lambda col: [{"name":str(k),"count":int(v)} for k,v in col.value_counts().items()]
        topic_rows = topics[topics["argument_id"].isin(ids)] if not topics.empty else pd.DataFrame()
        lower_courts = matched["lower_court"]
        if kind == "attorney":
            # The original attorney profile combines courts after stripping
            # parenthesized judge names, so one court is not split across bars.
            lower_courts = lower_courts.dropna().astype(str).str.replace(r"\s*\(.*\)", "", regex=True).str.strip()
        roster = []
        if kind == "firm":
            firm_people = participants[participants["firm"].eq(name)]
            for attorney, rows in firm_people.groupby("attorney_name"):
                count_args = rows["argument_id"].nunique()
                roster.append({"attorney_name": attorney, "arguments": count_args, "share": f"{count_args / len(matched) * 100:.1f}%"})
            roster.sort(key=lambda row: row["arguments"], reverse=True)
        yearly = matched.groupby(["term_year", "resolution_type"]).size().reset_index(name="count")
        resolution = {"total":len(matched),"resolved":len(resolved),"median":float(days.median()) if not days.empty else None,
                      "resolutions":count(matched["resolution_type"]),"case_types":count(matched["case_type"]),
                      "lower_courts":count(lower_courts),"outcomes":count(resolved["outcome"]),
                      "topics":count(topic_rows["topic"])[:15 if kind == "attorney" else 20] if not topic_rows.empty else [],"days":days.tolist(),
                      "roster":roster,"yearly":yearly.to_dict(orient="records"),
                      "percentiles":[float(days.quantile(q)) for q in (0.25, 0.5, 0.75)] if not days.empty else []}
    firm_info = data["firm_metadata"].get(name,{}) if kind == "firm" else {}
    members = sorted((row for row in data["attorneys"] if row.get("attorney_name") in profile.get("attorneys",[])), key=lambda row:row.get("total_arguments", 0), reverse=True) if kind == "firm" else []
    return {"profile":profile,"firm_info":firm_info,"members":members,"cases":cases,"dispositions":resolution}


@app.get("/api/firm-review")
def firm_review() -> dict:
    firms = oral_argument_people()["firms"]
    path = data_root() / "nh_supreme_court_firms_enriched_v7.csv"
    aliases, statuses = {}, {}
    if path.is_file():
        source = pd.read_csv(path, keep_default_na=False, encoding="utf-8")
        source = source[~source["review_status"].str.lower().str.startswith("skipped —") & source["full_name"].str.strip().ne("")]
        aliases = source.groupby("full_name")["short_name"].agg(lambda values: ", ".join(sorted(set(v for v in values if v)))).to_dict()
        statuses = source.groupby("full_name")["review_status"].agg(lambda values: " | ".join(sorted(set(v for v in values if v)))).to_dict()
    rows = [{"Canonical firm name": f["firm_name"], "Known abbreviation(s)": aliases.get(f["firm_name"], ""),
             "Arguments": f["total_arguments"], "Attorneys": f["unique_attorneys"], "Source review status": statuses.get(f["firm_name"], ""),
             "Feedback action": "Keep", "Merge / canonical target": "", "Notes": ""} for f in firms]
    return {"items": sorted(rows, key=lambda row: row["Canonical firm name"])}


def _person_dispositions(kind: str, name: str):
    from utils.data_loader import load_argument_dispositions, load_argument_participants
    dispositions, participants = load_argument_dispositions(), load_argument_participants()
    if dispositions.empty or participants.empty:
        return None
    column = "attorney_name" if kind == "attorney" else "firm"
    people = participants[participants[column].eq(name)]
    matched = dispositions[dispositions["argument_id"].isin(set(people["argument_id"]))]
    return (dispositions, people, matched) if not matched.empty else None


@app.get("/api/arguments/profile/dispositions.csv")
def person_dispositions_csv(kind: str = Query(pattern="^(attorney|firm)$"), name: str = Query(min_length=1, max_length=300)) -> Response:
    frames = _person_dispositions(kind, name)
    if frames is None:
        raise HTTPException(status_code=404, detail="Disposition data not found")
    _, participants, matched = frames
    columns = ["argument_id", "case_name", "argument_date", "term_year", "resolution_type", "disposition_date", "days_to_disposition", "outcome", "case_type", "lower_court", "author"]
    export = matched[columns].copy()
    if kind == "attorney":
        parts = participants[["argument_id", "side", "role", "firm", "source"]].rename(columns={"side":"attorney_side", "role":"attorney_role", "firm":"attorney_firm", "source":"roster_source"})
        export = export.merge(parts, on="argument_id", how="left")
    filename = re.sub(r"[^A-Za-z0-9_-]+", "_", name)
    return Response(export.to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{kind}_{filename}_dispositions.csv"'})


@app.get("/api/arguments/profile/cohort")
def attorney_cohort(name: str = Query(min_length=1, max_length=300), cohort: str = Query(default="all", pattern="^(all|case_type|period)$")) -> dict:
    frames = _person_dispositions("attorney", name)
    if frames is None:
        raise HTTPException(status_code=404, detail="Disposition data not found")
    all_cases, _, matched = frames
    description = "all attorneys and case types"
    comparison = all_cases
    if cohort == "case_type":
        primary = matched["case_type"].mode()
        if not primary.empty:
            comparison = all_cases[all_cases["case_type"].eq(primary.iloc[0])]
            description = f"attorneys in {primary.iloc[0]} cases"
        else:
            description = "all attorneys (no primary case type identified)"
    elif cohort == "period":
        start, end = matched["term_year"].min(), matched["term_year"].max()
        comparison = all_cases[all_cases["term_year"].between(start, end)]
        description = f"attorneys active {start}-{end}"
    def metrics(frame):
        resolved = frame[frame["resolution_type"].isin(["opinion", "case_order", "3jx_order", "multiple"])]
        days = pd.to_numeric(resolved["days_to_disposition"], errors="coerce").dropna()
        return {"match_rate":len(resolved)/len(frame)*100 if len(frame) else 0, "opinion_rate":float(frame["resolution_type"].eq("opinion").sum()/len(frame)*100) if len(frame) else 0, "median_days":float(days.median()) if not days.empty else None}
    return {"description":description, "size":len(comparison), "minimum":10, "attorney":metrics(matched), "cohort":metrics(comparison)}


# Register the parameterized route last, after the people and profile routes.
app.add_api_route("/api/arguments/{case_number}", argument_detail, methods=["GET"])
