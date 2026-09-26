"""Paths for data supplied by a verified runtime release.

``NHSC_DATA_ROOT`` is intentionally the *data* directory inside an installed
release, not the repository root.  Leaving it unset preserves the developer
checkout layout.
"""

from __future__ import annotations

import os
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def data_root() -> Path:
    """Return the immutable data directory for this process."""
    configured = os.environ.get("NHSC_DATA_ROOT", "").strip()
    return Path(configured).expanduser().resolve() if configured else REPOSITORY_ROOT / "data"


def production_runtime() -> bool:
    """Whether this process must never construct derived data on demand."""
    return os.environ.get("NHSC_RUNTIME_MODE", "").strip().lower() in {
        "1", "true", "yes", "production",
    }
