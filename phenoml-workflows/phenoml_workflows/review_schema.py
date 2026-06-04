from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

REVIEW_STATUSES = ("unreviewed", "needs_review", "approved", "rejected", "deferred")

REVIEW_FIELDS = (
    "review_status",
    "reviewer",
    "reviewed_at",
    "review_notes",
    "rationale",
    "target_override_table",
    "target_override_field",
    "needs_wg_decision",
)

REVIEW_DEFAULTS = {
    "review_status": "unreviewed",
    "reviewer": None,
    "reviewed_at": None,
    "review_notes": None,
    "rationale": None,
    "target_override_table": None,
    "target_override_field": None,
    "needs_wg_decision": False,
}

SOURCE_COLUMNS = (
    "concept_class_id",
    "concept_code",
    "concept_id",
    "concept_name",
    "domain_id",
    "is_mappable",
    "person_mapping_applied",
    "mapping_kind",
    "storage",
    "suggested_storage",
    "omop_target",
    "omop_table",
    "omop_field",
    "naaccr_person_column",
    "proposed_extension_table",
    "proposed_extension_column",
    "person_mapping_notes",
    "grain",
)

EXPORT_COLUMNS = SOURCE_COLUMNS + REVIEW_FIELDS


def mapping_key(mapping: dict[str, Any]) -> str:
    return f"{mapping.get('concept_class_id') or ''}::{mapping.get('concept_code') or ''}"


def display_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "yes", "y", "x"}


def normalize_review_field(field: str, value: Any) -> Any:
    if field == "review_status":
        status = (normalize_text(value) or "unreviewed").lower()
        return status
    if field == "needs_wg_decision":
        return normalize_bool(value)
    return normalize_text(value)


def review_payload_from_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    payload = dict(REVIEW_DEFAULTS)
    for field in REVIEW_FIELDS:
        if field in mapping:
            payload[field] = normalize_review_field(field, mapping.get(field))
    if payload["review_status"] not in REVIEW_STATUSES:
        payload["review_status"] = "unreviewed"
    return payload


def ensure_review_fields(mapping: dict[str, Any]) -> dict[str, Any]:
    for field, default in REVIEW_DEFAULTS.items():
        if field not in mapping:
            mapping[field] = default
        else:
            mapping[field] = normalize_review_field(field, mapping[field])

    if mapping["review_status"] not in REVIEW_STATUSES:
        mapping["review_status"] = "unreviewed"
    return mapping


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
