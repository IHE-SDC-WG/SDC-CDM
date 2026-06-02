from __future__ import annotations

from pathlib import Path
from typing import Any, Union

from .json_io import read_json, resolve_repo_path, write_json
from .review_schema import (
    REVIEW_FIELDS,
    REVIEW_STATUSES,
    ensure_review_fields,
    mapping_key,
    normalize_review_field,
)

DEFAULT_SPEC_PATH = "database/naaccr_omop/naaccr_omop_extension_mapping_spec.json"


def load_spec(path: Union[str, Path] = DEFAULT_SPEC_PATH) -> dict[str, Any]:
    spec = read_json(resolve_repo_path(path))
    for mapping in item_mappings(spec):
        ensure_review_fields(mapping)
    return spec


def save_spec(spec: dict[str, Any], path: Union[str, Path] = DEFAULT_SPEC_PATH) -> None:
    write_json(resolve_repo_path(path), spec)


def item_mappings(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return spec.get("workflow_input", {}).get("item_mappings", [])


def mapping_index(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {mapping_key(mapping): mapping for mapping in item_mappings(spec)}


def update_review_fields(
    *,
    spec: dict[str, Any],
    concept_class_id: str,
    concept_code: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    key = f"{concept_class_id}::{concept_code}"
    mapping = mapping_index(spec).get(key)
    if mapping is None:
        raise KeyError(f"Unknown mapping key: {key}")

    applied: dict[str, Any] = {}
    for field, value in updates.items():
        if field not in REVIEW_FIELDS:
            continue
        normalized = normalize_review_field(field, value)
        if field == "review_status" and normalized not in REVIEW_STATUSES:
            raise ValueError(f"Invalid review_status: {normalized}")
        mapping[field] = normalized
        applied[field] = normalized

    ensure_review_fields(mapping)
    return {"key": key, "applied": applied, "mapping": mapping}
