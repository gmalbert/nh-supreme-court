"""Build the CourtListener historical and reviewed combined corpus.

Examples:
  python scripts/courtlistener_integrate.py historical --artifacts-root artifacts
  python scripts/courtlistener_integrate.py combined --artifacts-root artifacts
  python scripts/courtlistener_integrate.py indexes --artifacts-root artifacts
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from utils.courtlistener_integration import IntegrationError, build_indexes, write_combined, write_historical


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely integrate CourtListener historical artifacts")
    parser.add_argument("command", choices=("historical", "combined", "indexes", "all"))
    parser.add_argument("--artifacts-root", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--promote", action="store_true", help="Replace live digest only after every merge gate passes")
    parser.add_argument("--reviewed-overlap", action="append", default=[], help="Reviewed source IDs joined with |")
    parser.add_argument("--modern-manifest", type=Path, help="Modern source metadata JSON or JSONL manifest")
    args = parser.parse_args()
    try:
        if args.command in ("historical", "all"):
            print(json.dumps(write_historical(args.artifacts_root), indent=2))
        if args.command in ("combined", "all"):
            print(json.dumps(write_combined(args.artifacts_root, promote=args.promote, reviewed_overlaps=set(args.reviewed_overlap), modern_manifest=args.modern_manifest), indent=2))
        if args.command in ("indexes", "all"):
            print(json.dumps(build_indexes(args.artifacts_root / "compiled" / "combined_case_digests.json", args.artifacts_root / "compiled"), indent=2))
    except IntegrationError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
