"""HTML/text and case-name normalization shared by every index."""

from __future__ import annotations

import html
import re

import pandas as pd


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def clean_text(value: object) -> str:
    """Strip HTML, unescape entities, and collapse whitespace."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = _TAG_RE.sub(" ", str(value))
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def normalize_case_name(value: str) -> str:
    """Normalize a case title for alias/citation comparison."""
    if not value:
        return ""
    lowered = value.casefold()
    lowered = lowered.replace("versus", " v ")
    lowered = re.sub(r"\bvs?\.?\b", " v ", lowered)
    lowered = _NON_ALNUM_RE.sub(" ", lowered)
    return _WS_RE.sub(" ", lowered).strip()


def normalize_citation(value: str) -> str:
    """Light normalization for U.S. Reports citations (e.g. '410 U.S. 113')."""
    if not value:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip().casefold()
    return text


def normalize_docket(value: str) -> str:
    """Normalize docket numbers; collapse spaces around punctuation."""
    if not value:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip().casefold()
    return text


def stable_case_id(href: str, name: str, term: str) -> str:
    import hashlib

    key = (href or f"{term}:{name}").strip()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]