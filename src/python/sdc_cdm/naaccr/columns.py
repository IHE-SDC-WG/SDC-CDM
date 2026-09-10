"""Stable SEER DTO to CSV mappings for the NAACCR dictionary."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

VERSION_FILE = "data_dictionary_version.csv"
SSDI_VERSION_FILE = "ssdi_version.csv"
DICTIONARY_FILE = "naaccr_item_dictionary.csv"
ALLOWED_CODE_FILE = "naaccr_item_allowed_code.csv"
REGISTRY_REQUIREMENT_FILE = "naaccr_item_registry_requirement.csv"

VERSION_COLUMNS = ("algorithm", "version", "naaccr_version", "source_api")
DICTIONARY_COLUMNS = (
    "item_num",
    "name",
    "xml_id",
    "section",
    "parent_xml_element",
    "data_type",
    "length",
    "record_types",
    "alternate_names",
    "source_of_standard",
    "allowable_values",
    "code_description",
    "code_note",
    "item_format",
    "description",
    "rationale",
    "general_notes",
    "clarification",
    "version_implemented",
    "year_implemented",
    "version_retired",
    "year_retired",
    "date_created",
    "date_modified",
)
ALLOWED_CODE_COLUMNS = ("item_num", "code_seq", "code", "description")
REGISTRY_REQUIREMENT_COLUMNS = (
    "item_num",
    "registry_code",
    "collect_status",
)

REGISTRY_COLLECT_FIELDS = (
    ("SEER", "seer_collect"),
    ("NPCR", "npcr_collect"),
    ("COC", "coc_collect"),
    ("CCCR", "cccr_collect"),
)


def _compact_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _item_number(item: Mapping[str, Any]) -> int:
    value = item.get("item_number")
    if value in (None, ""):
        raise ValueError("SEER NAACCR item is missing item_number")
    try:
        return int(str(value))
    except ValueError as exc:
        raise ValueError(f"invalid SEER NAACCR item_number: {value!r}") from exc


def dictionary_rows(items: Iterable[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for item in sorted(items, key=_item_number):
        rows.append(
            (
                _item_number(item),
                item.get("item_name"),
                item.get("xml_naaccr_id"),
                item.get("section"),
                item.get("xml_parent_id"),
                item.get("item_data_type"),
                item.get("item_length"),
                _compact_json(item.get("record_types")),
                _compact_json(item.get("alternate_names")),
                item.get("source_of_standard"),
                item.get("allowable_values"),
                item.get("code_description"),
                item.get("code_note"),
                item.get("format"),
                item.get("description"),
                item.get("rationale"),
                item.get("general_notes"),
                item.get("clarification"),
                item.get("version_implemented"),
                item.get("year_implemented"),
                item.get("version_retired"),
                item.get("year_retired"),
                item.get("date_created"),
                item.get("date_modified"),
            )
        )
    return rows


def allowed_code_rows(items: Iterable[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for item in sorted(items, key=_item_number):
        item_num = _item_number(item)
        codes = item.get("allowed_codes") or []
        if not isinstance(codes, Sequence) or isinstance(codes, (str, bytes)):
            raise TypeError(f"allowed_codes for item {item_num} must be an array")
        for code_seq, entry in enumerate(codes):
            if not isinstance(entry, Mapping):
                raise TypeError(
                    f"allowed_codes[{code_seq}] for item {item_num} must be an object"
                )
            code = entry.get("code")
            if code in (None, ""):
                raise ValueError(
                    f"allowed_codes[{code_seq}] for item {item_num} has no code"
                )
            rows.append((item_num, code_seq, code, entry.get("description")))
    return rows


def registry_requirement_rows(
    items: Iterable[Mapping[str, Any]],
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for item in sorted(items, key=_item_number):
        item_num = _item_number(item)
        for registry_code, field in REGISTRY_COLLECT_FIELDS:
            status = item.get(field)
            if status not in (None, ""):
                rows.append((item_num, registry_code, status))
    return rows
