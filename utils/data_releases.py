"""Immutable, hashed public data releases and app compatibility gates."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


SCHEMA_MAJOR = 1
SCHEMA_MINOR = 0


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_sha256(files: Iterable[str | Path]) -> str:
    digest = hashlib.sha256()
    for file_path in sorted((Path(path) for path in files), key=lambda path: path.name):
        digest.update(file_path.name.encode("utf-8"))
        digest.update(sha256_file(file_path).encode("ascii"))
    return digest.hexdigest()


def transformation_commit(root: str | Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_manifest(
    opinions: pd.DataFrame,
    release_files: Iterable[str | Path],
    *,
    release_id: str,
    transformation_commit_id: str = "unknown",
    known_exclusions: Iterable[str] = (),
) -> dict[str, Any]:
    files = [Path(path) for path in release_files]
    issued = pd.to_datetime(opinions.get("date_issued"), errors="coerce")
    missing_rate = float(issued.isna().mean()) if len(opinions) else 1.0
    pdf_urls = opinions.get("pdf_url", pd.Series("", index=opinions.index)).fillna("")
    source_coverage = float(pdf_urls.astype(str).str.len().gt(0).mean()) if len(opinions) else 0.0
    return {
        "release_id": release_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_major": SCHEMA_MAJOR,
        "schema_minor": SCHEMA_MINOR,
        "row_counts": {"opinions": int(len(opinions))},
        "source_coverage": {"opinion_pdf_url_rate": source_coverage},
        "quality": {"missing_decision_date_rate": missing_rate},
        "content_sha256": content_sha256(files),
        "files": [
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ],
        "known_exclusions": list(known_exclusions),
        "transformation_commit": transformation_commit_id,
    }


def assert_compatible(manifest: dict[str, Any]) -> None:
    if int(manifest.get("schema_major", -1)) != SCHEMA_MAJOR:
        raise RuntimeError("Unsupported corpus schema")
    missing_rate = float(
        manifest.get("quality", {}).get("missing_decision_date_rate", 1.0)
    )
    if missing_rate > 0.01:
        raise RuntimeError("Release fails decision-date gate")
    if not manifest.get("content_sha256"):
        raise RuntimeError("Release manifest has no content hash")


def create_release(
    opinions: pd.DataFrame,
    *,
    output_root: str | Path,
    release_id: str | None = None,
    known_exclusions: Iterable[str] = (),
    repo_root: str | Path | None = None,
) -> Path:
    """Create an immutable dated CSV/JSON snapshot and update latest.json."""
    root = Path(output_root)
    identifier = release_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    release_dir = root / identifier
    if release_dir.exists():
        raise FileExistsError(f"Release already exists: {release_dir}")
    release_dir.mkdir(parents=True)
    export = opinions.drop(columns=["opinion_text"], errors="ignore")
    csv_path = release_dir / "opinions.csv"
    json_path = release_dir / "opinions.json"
    export.to_csv(csv_path, index=False)
    export.to_json(json_path, orient="records", date_format="iso")
    manifest = build_manifest(
        export,
        [csv_path, json_path],
        release_id=identifier,
        transformation_commit_id=transformation_commit(repo_root or Path.cwd()),
        known_exclusions=known_exclusions,
    )
    assert_compatible(manifest)
    manifest_path = release_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    root.mkdir(parents=True, exist_ok=True)
    latest_path = root / "latest.json"
    latest_path.write_text(
        json.dumps(
            {
                "release_id": identifier,
                "manifest": f"{identifier}/manifest.json",
                "content_sha256": manifest["content_sha256"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def load_latest_manifest(output_root: str | Path) -> dict[str, Any] | None:
    root = Path(output_root)
    latest_path = root / "latest.json"
    if not latest_path.exists():
        return None
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    manifest_path = root / latest["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert_compatible(manifest)
    return manifest


def verify_release(release_dir: str | Path) -> dict[str, Any]:
    root = Path(release_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert_compatible(manifest)
    for expected in manifest.get("files", []):
        file_path = root / expected["name"]
        if not file_path.exists() or sha256_file(file_path) != expected["sha256"]:
            raise RuntimeError(f"Release file hash mismatch: {expected['name']}")
    return manifest
