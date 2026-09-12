"""Auditable local researcher workspaces and citation-ready packet exports."""

from __future__ import annotations

import io
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable


SCHEMA_VERSION = 1


def new_workspace(corpus_version: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "corpus_version": str(corpus_version),
        "items": [],
        "notes": [],
    }


def validate_workspace(workspace: dict[str, Any]) -> None:
    if int(workspace.get("schema_version", -1)) != SCHEMA_VERSION:
        raise ValueError("Unsupported workspace schema")
    if not workspace.get("corpus_version"):
        raise ValueError("Workspace must identify its corpus version")
    for item in workspace.get("items", []):
        if not item.get("case_id"):
            raise ValueError("Workspace items require a case_id")
        start = int(item.get("start", 0))
        end = int(item.get("end", start))
        if start < 0 or end < start:
            raise ValueError("Workspace item offsets are invalid")


def add_item(
    workspace: dict[str, Any],
    *,
    case_id: str,
    kind: str,
    start: int,
    end: int,
    page_number: int | None = None,
    source_url: str = "",
) -> dict[str, Any]:
    output = deepcopy(workspace)
    validate_workspace(output)
    item = {
        "case_id": str(case_id),
        "kind": str(kind),
        "start": int(start),
        "end": int(end),
    }
    if page_number is not None:
        item["page_number"] = int(page_number)
    if source_url:
        item["source_url"] = str(source_url)
    if item not in output["items"]:
        output["items"].append(item)
    validate_workspace(output)
    return output


def add_note(
    workspace: dict[str, Any],
    note: str,
    *,
    case_id: str | None = None,
) -> dict[str, Any]:
    output = deepcopy(workspace)
    validate_workspace(output)
    payload = {
        "text": str(note).strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if case_id:
        payload["case_id"] = str(case_id)
    if payload["text"]:
        output["notes"].append(payload)
    return output


def remove_item(workspace: dict[str, Any], index: int) -> dict[str, Any]:
    output = deepcopy(workspace)
    if 0 <= index < len(output.get("items", [])):
        output["items"].pop(index)
    return output


def resolve_workspace(
    workspace: dict[str, Any],
    resolver: Callable[[str], dict[str, Any] | None],
) -> dict[str, Any]:
    """Resolve display text at export time while retaining stored offsets."""
    validate_workspace(workspace)
    resolved_items = []
    for item in workspace["items"]:
        record = resolver(item["case_id"]) or {}
        text = str(record.get("text") or record.get("opinion_text") or "")
        start = min(int(item["start"]), len(text))
        end = min(int(item["end"]), len(text))
        resolved_items.append(
            {
                **item,
                "case_name": record.get("case_name") or item["case_id"],
                "citation": record.get("citation") or "",
                "source_url": item.get("source_url") or record.get("pdf_url") or "",
                "pinpoint": item.get("page_number")
                or record.get("page_number")
                or None,
                "source_span": text[start:end],
            }
        )
    return {
        **deepcopy(workspace),
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "items": resolved_items,
    }


def export_packet_json(resolved_workspace: dict[str, Any]) -> bytes:
    return json.dumps(
        resolved_workspace, indent=2, ensure_ascii=False, default=str
    ).encode("utf-8")


def export_packet_markdown(resolved_workspace: dict[str, Any]) -> str:
    lines = [
        "# Granite State Appeals Research Packet",
        "",
        f"- Corpus version: {resolved_workspace.get('corpus_version', '')}",
        f"- Retrieved: {resolved_workspace.get('resolved_at', '')}",
        "",
        "## Authorities and excerpts",
        "",
    ]
    for index, item in enumerate(resolved_workspace.get("items", []), 1):
        citation = item.get("citation") or item.get("case_id")
        pinpoint = item.get("pinpoint") or (
            f"characters {item.get('start')}-{item.get('end')}"
        )
        lines.extend(
            [
                f"### {index}. {item.get('case_name', item.get('case_id'))}",
                "",
                f"- Citation/docket: {citation}",
                f"- Source: {item.get('source_url') or 'Local corpus'}",
                f"- Pinpoint: {pinpoint}",
                "",
                f"> {item.get('source_span') or '[No text in the current corpus at these offsets]'}",
                "",
            ]
        )
    if resolved_workspace.get("notes"):
        lines.extend(["## Notes", ""])
        for note in resolved_workspace["notes"]:
            suffix = f" ({note['case_id']})" if note.get("case_id") else ""
            lines.append(f"- {note.get('text', '')}{suffix}")
    lines.extend(
        [
            "",
            "## Machine-readable appendix",
            "",
            json.dumps(
                resolved_workspace, indent=2, ensure_ascii=False, default=str
            ),
        ]
    )
    return "\n".join(lines)


def export_packet_pdf(resolved_workspace: dict[str, Any]) -> bytes:
    """Create a readable PDF packet; JSON remains the authoritative appendix."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Granite State Appeals Research Packet", styles["Title"]),
        Paragraph(
            f"Corpus version: {resolved_workspace.get('corpus_version', '')}",
            styles["BodyText"],
        ),
        Paragraph(
            f"Retrieved: {resolved_workspace.get('resolved_at', '')}",
            styles["BodyText"],
        ),
        Spacer(1, 12),
    ]
    for index, item in enumerate(resolved_workspace.get("items", []), 1):
        pinpoint = item.get("pinpoint") or (
            f"characters {item.get('start')}-{item.get('end')}"
        )
        story.append(
            Paragraph(
                f"{index}. {item.get('case_name', item.get('case_id'))}",
                styles["Heading2"],
            )
        )
        story.append(
            Paragraph(
                f"Citation/docket: {item.get('citation') or item.get('case_id')}<br/>"
                f"Source: {item.get('source_url') or 'Local corpus'}<br/>"
                f"Pinpoint: {pinpoint}",
                styles["BodyText"],
            )
        )
        safe_span = (
            str(item.get("source_span") or "[No text at these offsets]")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        story.append(Paragraph(safe_span, styles["BodyText"]))
        story.append(Spacer(1, 12))
    if resolved_workspace.get("notes"):
        story.append(PageBreak())
        story.append(Paragraph("Notes", styles["Heading1"]))
        for note in resolved_workspace["notes"]:
            story.append(Paragraph(str(note.get("text", "")), styles["BodyText"]))
    document.build(story)
    return buffer.getvalue()
