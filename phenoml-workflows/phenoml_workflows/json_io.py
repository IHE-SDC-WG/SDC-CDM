from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent


def resolve_repo_path(path: Union[str, Path]) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def resolve_package_path(path: Union[str, Path]) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if str(candidate).startswith("phenoml-workflows/"):
        return REPO_ROOT / candidate
    return PACKAGE_ROOT / candidate


def read_json(path: Union[str, Path]) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Union[str, Path], value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
