"""Copy the current verified runtime release and replace staging profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.runtime_release import sha256_file, verify_runtime_release


APPLICATION = "nh-supreme-court"
PRODUCTION_POINTER = "releases/nh-supreme-court/current.json"
def _s3_copy(bucket: str, key: str, destination: Path, endpoint: str) -> None:
    if not key.startswith("releases/nh-supreme-court/") or ".." in PurePosixPath(key).parts:
        raise ValueError("The runtime pointer contains an unsafe R2 object key")
    subprocess.run(
        ["aws", "s3", "cp", f"s3://{bucket}/{key}", str(destination), "--endpoint-url", endpoint, "--no-progress"],
        check=True,
    )


def _extract_checked_archive(archive: Path, destination: Path, release_id: str) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != release_id:
                raise ValueError("The runtime archive contains an unsafe path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("The runtime archive contains an unsupported entry")
        bundle.extractall(destination)
    return destination / release_id


def build_release(pointer_path: Path, archive_path: Path, manifest_path: Path,
                  stats_path: Path, output_root: Path, release_id: str,
                  source_commit: str) -> tuple[Path, Path]:
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if pointer.get("application") != APPLICATION:
        raise ValueError("The source pointer belongs to another application")
    source_id = pointer.get("release_id", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", source_id) or source_id in (".", ".."):
        raise ValueError("The source pointer contains an invalid release ID")
    if sha256_file(archive_path) != pointer.get("archive_sha256"):
        raise ValueError("The source runtime archive checksum does not match its pointer")

    output_root.mkdir(parents=True, exist_ok=True)
    release_dir = output_root / release_id
    if release_dir.exists():
        raise FileExistsError(f"Release already exists: {release_dir}")
    with tempfile.TemporaryDirectory(prefix="nhsc-staging-release-") as temp_dir:
        extracted = _extract_checked_archive(archive_path, Path(temp_dir), source_id)
        embedded_manifest = extracted / "manifest.json"
        if json.loads(embedded_manifest.read_text(encoding="utf-8")) != json.loads(manifest_path.read_text(encoding="utf-8")):
            raise ValueError("The downloaded manifest does not match the runtime archive")
        verify_runtime_release(extracted)
        staged = output_root / f".{release_id}.incoming"
        if staged.exists():
            shutil.rmtree(staged)
        shutil.copytree(extracted, staged)
        stats_destination = staged / "data" / "processed" / "oral_arguments_attorney_stats.json"
        stats_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stats_path, stats_destination)

        manifest = json.loads((staged / "manifest.json").read_text(encoding="utf-8"))
        manifest["release_id"] = release_id
        manifest["source_commit"] = source_commit
        manifest["built_at"] = datetime.now(timezone.utc).isoformat()
        relative = "data/processed/oral_arguments_attorney_stats.json"
        entry = {"path": relative, "bytes": stats_destination.stat().st_size,
                 "sha256": sha256_file(stats_destination)}
        files = {row["path"]: row for row in manifest.get("files", [])}
        files[relative] = entry
        manifest["files"] = [files[key] for key in sorted(files)]
        (staged / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        verify_runtime_release(staged)
        shutil.move(str(staged), str(release_dir))

    archive_out = output_root / f"{release_id}.tar.gz"
    with tarfile.open(archive_out, "w:gz") as bundle:
        bundle.add(release_dir, arcname=release_id)
    return release_dir, archive_out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-root", type=Path, default=Path("dist/releases"))
    parser.add_argument("--stats-file", type=Path, default=Path("data/processed/oral_arguments_attorney_stats.json"))
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.release_id) or args.release_id in (".", ".."):
        raise SystemExit("Invalid release ID")
    bucket = os.environ["R2_BUCKET"]
    endpoint = f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    with tempfile.TemporaryDirectory(prefix="nhsc-staging-source-") as temp_dir:
        work = Path(temp_dir)
        pointer_path, archive_path, manifest_path = work / "current.json", work / "runtime.tar.gz", work / "manifest.json"
        _s3_copy(bucket, PRODUCTION_POINTER, pointer_path, endpoint)
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        _s3_copy(bucket, pointer.get("archive", ""), archive_path, endpoint)
        _s3_copy(bucket, pointer.get("manifest", ""), manifest_path, endpoint)
        release_dir, archive_out = build_release(
            pointer_path, archive_path, manifest_path, args.stats_file,
            args.output_root, args.release_id, args.source_commit,
        )
        prefix = f"releases/nh-supreme-court/staging/{args.release_id}"
        pointer_out = {
            "application": APPLICATION,
            "release_id": args.release_id,
            "archive": f"{prefix}/runtime.tar.gz",
            "manifest": f"{prefix}/manifest.json",
            "archive_sha256": sha256_file(archive_out),
        }
        (args.output_root.parent / "staging-current.json").write_text(
            json.dumps(pointer_out, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
