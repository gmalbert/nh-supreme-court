"""Build the optional dense opinion embedding artifact."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.data_loader import load_opinions
from utils.semantic_search import build_opinion_embeddings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=32)
    arguments = parser.parse_args()
    path = build_opinion_embeddings(
        load_opinions(), batch_size=arguments.batch_size
    )
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
