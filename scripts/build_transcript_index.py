"""Build overlapping transcript chunks from per-term transcript parquets.

Output: data/retrieval/transcript_chunks.parquet

Each chunk spans up to ``turns_per_chunk`` turns with ``overlap`` turns shared
between adjacent chunks so multi-turn Q&A spans still match.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted((ROOT / "data").glob("transcripts_*.parquet"))
OUT = ROOT / "data" / "retrieval" / "transcript_chunks.parquet"


def chunk_group(records, turns_per_chunk: int = 6, overlap: int = 2):
    step = max(1, turns_per_chunk - overlap)
    for start_idx in range(0, len(records), step):
        turns = records[start_idx : start_idx + turns_per_chunk]
        if not turns:
            continue
        text = "\n".join(
            f"{turn['speaker_name']}: {turn['text']}"
            for turn in turns
            if turn.get("text")
        )
        if len(text) < 80:
            continue
        first, last = turns[0], turns[-1]
        speaker_set = sorted(
            {turn["speaker_name"] for turn in turns if turn.get("speaker_name")}
        )
        yield {
            "chunk_id": f"{first['argument_id']}:{first['section_idx']}:{first['turn_idx']}",
            "argument_id": first["argument_id"],
            "argument_title": first["argument_title"],
            "term": first["term"],
            "section_title": first["section_title"],
            "start": first["start"],
            "stop": last["stop"],
            "speakers": speaker_set,
            "text": text,
        }


def main() -> None:
    if not FILES:
        print("No transcript parquets found.")
        return
    frames = [pd.read_parquet(path) for path in FILES]
    turns = pd.concat(frames, ignore_index=True)
    chunks = []
    for _, group in turns.groupby(["argument_id", "section_idx"], sort=False):
        records = group.sort_values(["section_idx", "turn_idx"]).to_dict("records")
        chunks.extend(chunk_group(records))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(chunks).to_parquet(OUT, index=False, compression="zstd")
    print(f"Wrote {len(chunks)} transcript chunks -> {OUT}")


if __name__ == "__main__":
    main()