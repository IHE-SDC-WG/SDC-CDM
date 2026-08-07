"""Repository path helpers."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MANIFEST_PATH = REPO_ROOT / "database" / "manifest.json"


def repository_path(relative_path: str) -> Path:
    """Resolve a validated repo-relative POSIX path."""

    return REPO_ROOT / Path(relative_path)
