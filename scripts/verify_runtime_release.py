"""Verify a previously assembled runtime release without importing Streamlit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.runtime_release import verify_runtime_release


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", type=Path)
    args = parser.parse_args()
    manifest = verify_runtime_release(args.release_dir)
    print(json.dumps({"release_id": manifest["release_id"], "files": len(manifest["files"]) }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
