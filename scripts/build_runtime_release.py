"""Create a local, immutable runtime release ready for R2 publication."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.runtime_release import build_runtime_release


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=ROOT / "dist" / "releases")
    parser.add_argument("--release-id")
    args = parser.parse_args()
    release_id = args.release_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    release_dir = build_runtime_release(ROOT, args.output_root, release_id=release_id)
    print(release_dir)
    print(args.output_root / f"{release_id}.tar.gz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
