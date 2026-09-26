"""Create and verify immutable, runtime-only Granite State Appeals releases."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


APPLICATION = "nh-supreme-court"
MANIFEST_SCHEMA_VERSION = 1
ARCHIVE_NAME = "runtime.tar.gz"

# These paths are deliberately a small, reviewable boundary.  Raw PDFs,
# scraper caches, source downloads, virtual environments, and build logs are
# never reachable from it.
RUNTIME_TREES = ("data/processed", "data/retrieval", "data/oral_argument_pdf_dates")
RUNTIME_FILES = (
    "data/justices.json",
    "data/topic_taxonomy.json",
    "data/nh_supreme_court_firms_enriched_v7.csv",
    "data/pending_oral_argument_cases.csv",
    "data/citation_overrides.json",
)
BUILD_ONLY_FILENAMES = {
    "opinion_embeddings.npz",
    "opinion_embeddings.meta.json",
    "case_embeddings.npy",
    "case_embedding_meta.json",
}
REQUIRED_FILES = (
    "data/processed/opinions.csv",
    "data/processed/all_opinions.json",
    "data/processed/case_orders.csv",
    "data/processed/oral_arguments.json",
    "data/processed/oral_argument_stats.json",
    "data/retrieval/case_documents.parquet",
    "data/justices.json",
    "data/topic_taxonomy.json",
    "data/citation_overrides.json",
)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _safe_relative(path: str) -> Path:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Unsafe release path: {path}")
    return Path(*candidate.parts)


def _runtime_sources(root: Path) -> Iterable[tuple[Path, Path]]:
    for relative in RUNTIME_TREES:
        source = root / relative
        if not source.exists():
            continue
        for child in sorted(source.rglob("*")):
            if child.is_file() and child.name not in BUILD_ONLY_FILENAMES:
                yield child, child.relative_to(root)
    for relative in RUNTIME_FILES:
        source = root / relative
        if source.is_file():
            yield source, Path(relative)


def _file_entries(release_dir: Path) -> list[dict[str, Any]]:
    entries = []
    for path in sorted(release_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            entries.append(
                {
                    "path": path.relative_to(release_dir).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return entries


def build_runtime_release(
    repository_root: str | Path,
    output_root: str | Path,
    *,
    release_id: str,
    source_commit: str | None = None,
) -> Path:
    """Build a release directory and compressed archive without publishing it."""
    root = Path(repository_root).resolve()
    output = Path(output_root).resolve()
    release_dir = output / release_id
    if release_dir.exists():
        raise FileExistsError(f"Release already exists: {release_dir}")
    release_dir.mkdir(parents=True)

    for source, relative in _runtime_sources(root):
        destination = release_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    files = _file_entries(release_dir)
    manifest = {
        "application": APPLICATION,
        "release_id": release_id,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "source_commit": source_commit or _git_commit(root),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "runtime_allowlist": {"trees": list(RUNTIME_TREES), "files": list(RUNTIME_FILES)},
        "required_files": list(REQUIRED_FILES),
        "files": files,
    }
    (release_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verify_runtime_release(release_dir)

    archive = output / f"{release_id}.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(release_dir, arcname=release_id)
    return release_dir


def load_runtime_manifest(release_dir: str | Path) -> dict[str, Any]:
    path = Path(release_dir) / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def verify_runtime_release(release_dir: str | Path) -> dict[str, Any]:
    """Validate schema, required files, and all release checksums."""
    root = Path(release_dir).resolve()
    manifest = load_runtime_manifest(root)
    if manifest.get("application") != APPLICATION:
        raise RuntimeError("Release belongs to a different application")
    if manifest.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        raise RuntimeError("Unsupported runtime release manifest schema")
    if not manifest.get("release_id") or not manifest.get("source_commit"):
        raise RuntimeError("Release metadata is incomplete")

    expected = {entry["path"]: entry for entry in manifest.get("files", [])}
    for relative, entry in expected.items():
        file_path = root / _safe_relative(relative)
        if not file_path.is_file() or file_path.stat().st_size != entry.get("bytes"):
            raise RuntimeError(f"Release file is missing or has wrong size: {relative}")
        if sha256_file(file_path) != entry.get("sha256"):
            raise RuntimeError(f"Release file hash mismatch: {relative}")
    for relative in manifest.get("required_files", []):
        if relative not in expected:
            raise RuntimeError(f"Required file is absent from manifest: {relative}")
    return manifest
