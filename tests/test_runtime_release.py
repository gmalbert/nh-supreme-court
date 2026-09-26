from __future__ import annotations

import hashlib
import json

import pytest

from utils.runtime_release import (
    APPLICATION,
    BUILD_ONLY_FILENAMES,
    MANIFEST_SCHEMA_VERSION,
    verify_runtime_release,
)


def test_embedding_artifacts_are_explicitly_build_only():
    assert "opinion_embeddings.npz" in BUILD_ONLY_FILENAMES
    assert "case_embeddings.npy" in BUILD_ONLY_FILENAMES


def _write_release(tmp_path, *, schema=MANIFEST_SCHEMA_VERSION, include_optional=True):
    required = "data/processed/opinions.csv"
    payload = b"case_number,case_name\n2026-1,Example\n"
    target = tmp_path / required
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    files = [{"path": required, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}]
    if include_optional:
        optional = tmp_path / "data/processed/optional.json"
        optional.write_text("{}", encoding="utf-8")
        files.append({"path": "data/processed/optional.json", "bytes": 2, "sha256": hashlib.sha256(b"{}").hexdigest()})
    manifest = {
        "application": APPLICATION,
        "release_id": "test-release",
        "manifest_schema_version": schema,
        "source_commit": "a" * 40,
        "required_files": [required],
        "files": files,
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return target


def test_verify_runtime_release_accepts_optional_files_absent(tmp_path):
    _write_release(tmp_path, include_optional=False)
    assert verify_runtime_release(tmp_path)["release_id"] == "test-release"


def test_verify_runtime_release_rejects_bad_checksum(tmp_path):
    target = _write_release(tmp_path)
    target.write_bytes(b"x" * target.stat().st_size)
    with pytest.raises(RuntimeError, match="hash mismatch"):
        verify_runtime_release(tmp_path)


def test_verify_runtime_release_rejects_incompatible_metadata(tmp_path):
    _write_release(tmp_path, schema=MANIFEST_SCHEMA_VERSION + 1)
    with pytest.raises(RuntimeError, match="Unsupported"):
        verify_runtime_release(tmp_path)


def test_verify_runtime_release_rejects_missing_required_file(tmp_path):
    _write_release(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifest["required_files"].append("data/processed/required-but-absent.json")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Required file"):
        verify_runtime_release(tmp_path)
