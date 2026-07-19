"""Build dense case embeddings with sentence-transformers.

Output:
    data/retrieval/case_embeddings.npy
    data/retrieval/case_embedding_meta.json

Requires ``sentence-transformers`` and a working torch backend.  On machines
without those (e.g. CI with broken torch wheels), this script prints an
informative note and exits cleanly — the RetrievalService degrades to lexical
retrieval automatically.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "retrieval"
MODEL_ID = "BAAI/bge-base-en-v1.5"


def main() -> None:
    try:
        import numpy as np
        import pandas as pd
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # pragma: no cover
        print(f"Dense index build skipped ({exc}).")
        print("The retrieval service will run in lexical-only mode.")
        return

    docs_path = DATA / "case_documents.parquet"
    if not docs_path.exists():
        print("case_documents.parquet missing. Run build_retrieval_corpus.py first.")
        return

    docs = pd.read_parquet(docs_path)
    model = SentenceTransformer(MODEL_ID)
    # bge-small-en-v1.5 uses NO instruction prefix for corpus passages.
    texts = list(docs["retrieval_text"])
    embeddings = model.encode(
        texts,
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).astype("float32")
    np.save(DATA / "case_embeddings.npy", embeddings)
    (DATA / "case_embedding_meta.json").write_text(
        json.dumps(
            {
                "model": MODEL_ID,
                "rows": int(len(docs)),
                "dimensions": int(embeddings.shape[1]),
                "normalized": True,
                "corpus_file": "case_documents.parquet",
            },
            indent=2,
        )
    )
    print(
        f"Wrote {embeddings.shape[0]}x{embeddings.shape[1]} embeddings -> "
        f"{DATA / 'case_embeddings.npy'}"
    )


if __name__ == "__main__":
    main()