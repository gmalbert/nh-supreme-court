"""Safe in-browser opinion PDF rendering helpers."""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path
from urllib.parse import quote

import streamlit as st


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
CITATION_RE = re.compile(r"\b(?:\d{1,3}\s+N\.H\.\s+\d+|\d{4}-\d{3,4})\b")


def extract_key_passages(
    text: str,
    *,
    summary: str = "",
    limit_per_kind: int = 2,
) -> list[dict[str, object]]:
    """Extract evidence-linked holding, dissent, and citation passages.

    This intentionally uses transparent rules.  Every result carries character
    offsets so the UI can show exactly what was highlighted and a native PDF
    viewer can search for the same phrase.
    """
    source = str(text or "")
    if not source.strip():
        return []
    sentences = [part.strip() for part in SENTENCE_RE.split(source) if len(part.split()) >= 6]
    summary_tokens = set(re.findall(r"[a-z]{4,}", str(summary).lower()))
    candidates: list[tuple[int, str, str]] = []
    cursor = 0
    for sentence in sentences:
        start = source.find(sentence, cursor)
        if start < 0:
            start = source.find(sentence)
        cursor = max(cursor, start + len(sentence))
        lowered = sentence.lower()
        if re.search(r"\b(?:we hold|we conclude|we determine|accordingly|therefore)\b", lowered):
            candidates.append((start, "Holding", sentence))
        if re.search(r"\b(?:dissent|dissenting|respectfully disagree)\b", lowered):
            candidates.append((start, "Dissent", sentence))
        if CITATION_RE.search(sentence):
            candidates.append((start, "Cited authority", sentence))

    # Sentence tokenizers often split reporter abbreviations such as "N.H.".
    # Extract citation windows directly from the original text as a second,
    # offset-preserving pass.
    for citation in CITATION_RE.finditer(source):
        start = max(source.rfind(".", 0, citation.start()) + 1, 0)
        while start < len(source) and source[start].isspace():
            start += 1
        stop = source.find(".", citation.end())
        end = len(source) if stop < 0 else stop + 1
        passage = source[start:end].strip()
        adjusted_start = source.find(passage, start, end) if passage else start
        if passage:
            candidates.append((adjusted_start, "Cited authority", passage))

    if summary_tokens:
        best = max(
            sentences,
            key=lambda sentence: len(
                summary_tokens & set(re.findall(r"[a-z]{4,}", sentence.lower()))
            ),
        )
        overlap = len(summary_tokens & set(re.findall(r"[a-z]{4,}", best.lower())))
        if overlap:
            candidates.append((source.find(best), "Holding", best))

    output: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    seen: set[tuple[str, int]] = set()
    for start, kind, passage in sorted(candidates, key=lambda item: item[0]):
        key = (kind, start)
        if key in seen or counts.get(kind, 0) >= limit_per_kind:
            continue
        seen.add(key)
        counts[kind] = counts.get(kind, 0) + 1
        words = passage.split()
        search_term = " ".join(words[: min(10, len(words))])
        output.append(
            {
                "kind": kind,
                "passage": passage,
                "start": max(0, start),
                "end": max(0, start) + len(passage),
                "search_term": search_term,
            }
        )
    return output


def render_opinion_pdf(
    docket: str,
    *,
    pdf_url: str = "",
    pdf_path: str | Path | None = None,
    highlights: list[dict[str, object]] | None = None,
    height: int = 760,
) -> None:
    """Render a PDF with native-search highlighting and exact passage cards."""
    local = Path(pdf_path) if pdf_path else None
    source = ""
    if local and local.exists():
        encoded = base64.b64encode(local.read_bytes()).decode("ascii")
        source = f"data:application/pdf;base64,{encoded}"
    elif pdf_url:
        source = pdf_url
    if source:
        selected = None
        if highlights:
            selected = st.selectbox(
                "Highlight key passage in PDF",
                highlights,
                format_func=lambda item: (
                    f"{item['kind']} · characters {item['start']}–{item['end']}"
                ),
                key=f"pdf_highlight_{docket}",
            )
            fragment = quote(str(selected.get("search_term", "")))
            if fragment:
                source = f"{source.split('#', 1)[0]}#search={fragment}"
        st.components.v1.html(
            f'<iframe title="Opinion PDF {docket}" src="{source}" '
            f'width="100%" height="{int(height)}" style="border:1px solid #d5dbe3"></iframe>',
            height=height + 10,
            scrolling=True,
        )
        st.link_button("Open official PDF in a new tab", pdf_url or source)
        if highlights:
            st.markdown("#### Extracted key passages")
            for item in highlights:
                passage = html.escape(str(item.get("passage", "")))
                st.markdown(
                    f"**{item.get('kind', 'Passage')}** · characters "
                    f"{item.get('start', 0)}–{item.get('end', 0)}<br>"
                    f"<mark>{passage}</mark>",
                    unsafe_allow_html=True,
                )
        return
    official = f"https://www.courts.nh.gov/content/opinions/archive/{quote(str(docket))}"
    st.info(f"A PDF for {docket} is not available in the local corpus.")
    st.link_button("Search the NH Courts opinion archive", official)
