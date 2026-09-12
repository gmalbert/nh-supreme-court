"""Dependency-light readability metrics for judicial opinions."""

from __future__ import annotations

import re

import pandas as pd


WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
SENTENCE_RE = re.compile(r"[.!?]+(?:\s+|$)")


def _syllables(word: str) -> int:
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups)
    if word.endswith("e") and not word.endswith(("le", "ye")) and count > 1:
        count -= 1
    return max(1, count)


def compute_readability(text: str) -> dict[str, float | int]:
    """Compute Flesch, Flesch-Kincaid, Gunning Fog, and length metrics."""
    text = str(text or "")
    words = WORD_RE.findall(text)
    if len(words) < 20:
        return {}
    sentences = max(1, len(SENTENCE_RE.findall(text)))
    syllables = sum(_syllables(word) for word in words)
    complex_words = sum(1 for word in words if _syllables(word) >= 3)
    words_per_sentence = len(words) / sentences
    syllables_per_word = syllables / len(words)
    return {
        "flesch_reading_ease": round(
            206.835 - 1.015 * words_per_sentence - 84.6 * syllables_per_word, 2
        ),
        "flesch_kincaid_grade": round(
            0.39 * words_per_sentence + 11.8 * syllables_per_word - 15.59, 2
        ),
        "fog_index": round(
            0.4 * (words_per_sentence + 100 * complex_words / len(words)), 2
        ),
        "avg_sentence_length": round(words_per_sentence, 2),
        "word_count": len(words),
    }


def add_readability_scores(
    frame: pd.DataFrame, text_col: str = "opinion_text"
) -> pd.DataFrame:
    scores = frame.get(text_col, pd.Series("", index=frame.index)).map(compute_readability)
    metrics = pd.DataFrame(scores.tolist(), index=frame.index)
    return pd.concat([frame.copy(), metrics], axis=1)
