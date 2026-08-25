"""Fetch SEER staging metadata and emit the normalized SSDI CSV contract."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sdc_cdm.naaccr.client import BASE_URL, SeerApiClient, SeerApiError
from sdc_cdm.naaccr.columns import VERSION_COLUMNS, VERSION_FILE
from sdc_cdm.naaccr.csv_io import DEFAULT_CSV_DIR, write_csv

STAGING_SCHEMA_COLUMNS = ("schema_id_number", "schema_id", "schema_name")
SELECTION_RULE_COLUMNS = (
    "schema_id_number",
    "site",
    "histology",
    "behavior",
    "sex_at_birth",
    "discriminator_1",
    "discriminator_2",
    "year_dx",
)
SSDI_ITEM_COLUMNS = ("item_num", "name", "xml_id", "unit", "decimal_places")
SCHEMA_ITEM_COLUMNS = (
    "schema_id_number",
    "item_num",
    "item_role",
    "used_for_staging",
    "default_value",
    "description",
    "rationale",
    "additional_info",
    "table_notes",
    "coding_guidelines",
)
REGISTRY_COLUMNS = ("code", "name")
SCHEMA_ITEM_REQUIREMENT_COLUMNS = (
    "schema_id_number",
    "item_num",
    "registry_code",
    "is_required",
)
SCHEMA_ITEM_CODE_COLUMNS = (
    "schema_id_number",
    "item_num",
    "code",
    "description",
)
STAGING_TABLE_COLUMNS = (
    "table_key",
    "name",
    "title",
    "subtitle",
    "description",
    "notes",
    "coding_guidelines",
)
STAGING_TABLE_COLUMN_COLUMNS = (
    "table_key",
    "col_index",
    "col_key",
    "col_name",
    "col_type",
    "col_source",
)
STAGING_TABLE_ROW_COLUMNS = ("table_key", "row_index", "cells")
SCHEMA_INVOLVED_TABLE_COLUMNS = ("schema_id_number", "table_key")

# Order is part of the public producer/loader contract.
SSDI_CONTRACT: dict[str, tuple[str, ...]] = {
    "staging_schema.csv": STAGING_SCHEMA_COLUMNS,
    "schema_selection_rule.csv": SELECTION_RULE_COLUMNS,
    "naaccr_item.csv": SSDI_ITEM_COLUMNS,
    "schema_item.csv": SCHEMA_ITEM_COLUMNS,
    "registry.csv": REGISTRY_COLUMNS,
    "schema_item_requirement.csv": SCHEMA_ITEM_REQUIREMENT_COLUMNS,
    "schema_item_code.csv": SCHEMA_ITEM_CODE_COLUMNS,
    "staging_table.csv": STAGING_TABLE_COLUMNS,
    "staging_table_column.csv": STAGING_TABLE_COLUMN_COLUMNS,
    "staging_table_row.csv": STAGING_TABLE_ROW_COLUMNS,
    "schema_involved_table.csv": SCHEMA_INVOLVED_TABLE_COLUMNS,
}
SSDI_FILES = (VERSION_FILE, *SSDI_CONTRACT)
STATIC_REGISTRIES = (
    ("SEER", "SEER"),
    ("NPCR", "NPCR"),
    ("COC", "COC"),
    ("CCCR", "CCCR"),
)


@dataclass(frozen=True)
class SsdiFetchResult:
    algorithm: str
    staging_version: str
    naaccr_version: str
    schema_count: int
    item_count: int
    table_count: int
    involved_table_count: int


@dataclass(frozen=True)
class _Schema:
    number: str
    payload: dict[str, Any]


def _array(value: Any, label: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SeerApiError(f"SEER {label} must be an array")
    return value


def _objects(value: Any, label: str) -> list[dict[str, Any]]:
    entries = _array(value, label)
    if not all(isinstance(entry, dict) for entry in entries):
        raise SeerApiError(f"SEER {label} must contain objects")
    return entries


def _schema_number(schema: Mapping[str, Any]) -> str | None:
    for output in _objects(schema.get("outputs"), "staging schema outputs"):
        if output.get("key") == "naaccr_schema_id":
            value = output.get("default")
            return None if value in (None, "") else str(value)
    return None


def _sorted_schemas(payloads: Iterable[dict[str, Any]]) -> list[_Schema]:
    schemas: list[tuple[int, _Schema]] = []
    for payload in payloads:
        number = _schema_number(payload)
        if number is None:
            continue
        try:
            numeric = int(number)
        except ValueError as exc:
            raise SeerApiError(
                f"SEER staging schema has nonnumeric naaccr_schema_id: {number!r}"
            ) from exc
        schemas.append((numeric, _Schema(number=number, payload=payload)))
    schemas.sort(key=lambda entry: entry[0])
    return [schema for _numeric, schema in schemas]


def _is_ssdi(item: Mapping[str, Any]) -> bool:
    return any(
        metadata.get("name") == "SSDI"
        for metadata in _objects(item.get("metadata"), "staging input metadata")
    )


def _item_sort_key(item: Mapping[str, Any]) -> int:
    value = item.get("naaccr_item")
    if value in (None, ""):
        return 0
    try:
        return int(str(value))
    except ValueError as exc:
        raise SeerApiError(f"invalid staging naaccr_item: {value!r}") from exc


def _table_id(item: Mapping[str, Any]) -> str | None:
    value = item.get("table")
    return None if value in (None, "") else str(value)


def _append_unique(values: list[str], seen: set[str], value: str | None) -> None:
    if value is not None and value not in seen:
        values.append(value)
        seen.add(value)


def _table_and_link_order(
    schemas: list[_Schema],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Keep the prior producer order, then append omitted non-SSDI inputs."""

    table_ids: list[str] = []
    seen_tables: set[str] = set()
    links: list[tuple[str, str]] = []
    seen_links: set[tuple[str, str]] = set()

    def add(schema_number: str, table_id: str | None) -> None:
        _append_unique(table_ids, seen_tables, table_id)
        if table_id is not None:
            link = (schema_number, table_id)
            if link not in seen_links:
                links.append(link)
                seen_links.add(link)

    # This is the historical TypeScript order. Its output loop skipped
    # nonnumeric NAACCR outputs before fetching their tables.
    for schema in schemas:
        payload = schema.payload
        selection = payload.get("schema_selection_table")
        add(schema.number, None if selection in (None, "") else str(selection))
        inputs = _objects(payload.get("inputs"), "staging schema inputs")
        for item in sorted(
            (item for item in inputs if _is_ssdi(item)), key=_item_sort_key
        ):
            add(schema.number, _table_id(item))
        for item in _objects(payload.get("outputs"), "staging schema outputs"):
            item_number = item.get("naaccr_item")
            if isinstance(item_number, int) and not isinstance(item_number, bool):
                add(schema.number, _table_id(item))

    # Include tables attached to non-NAACCR outputs without disturbing the
    # historical prefix.
    for schema in schemas:
        for item in _objects(schema.payload.get("outputs"), "staging schema outputs"):
            item_number = item.get("naaccr_item")
            if not isinstance(item_number, int) or isinstance(item_number, bool):
                add(schema.number, _table_id(item))

    # Correct the historical omission without reordering the existing rows.
    for schema in schemas:
        for item in _objects(schema.payload.get("inputs"), "staging schema inputs"):
            if not _is_ssdi(item):
                add(schema.number, _table_id(item))
    return table_ids, links


def _table_map(
    table_ids: list[str], tables: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if len(table_ids) != len(tables):
        raise SeerApiError("SEER staging table response count changed during fetch")
    result: dict[str, dict[str, Any]] = {}
    for requested_id, table in zip(table_ids, tables, strict=True):
        response_id = table.get("id")
        if response_id not in (None, "", requested_id):
            raise SeerApiError(
                f"SEER staging table id mismatch: requested {requested_id!r}, got {response_id!r}"
            )
        result[requested_id] = table
    return result


def _table_text(table: Mapping[str, Any] | None, field: str) -> Any:
    return None if table is None else table.get(field)


def _bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def _description_index(table: Mapping[str, Any]) -> int:
    definitions = _objects(table.get("definition"), "staging table definition")
    for index, definition in enumerate(definitions):
        if str(definition.get("key") or "").lower() == "description":
            return index
    return -1


def _code_rows(
    schema_number: str,
    item_number: Any,
    table: Mapping[str, Any] | None,
) -> list[tuple[Any, ...]]:
    if table is None:
        return []
    description_index = _description_index(table)
    result: list[tuple[Any, ...]] = []
    for row in _array(table.get("rows"), "staging table rows"):
        if not isinstance(row, list):
            raise SeerApiError("SEER staging table rows must contain arrays")
        code = row[0] if row else None
        description = (
            row[description_index]
            if description_index >= 0 and description_index < len(row)
            else None
        )
        result.append((schema_number, item_number, code, description))
    return result


def _selection_rows(
    schema: _Schema, table: Mapping[str, Any] | None
) -> list[tuple[Any, ...]]:
    if table is None:
        return []
    definitions = _objects(table.get("definition"), "staging table definition")
    positions = {
        str(definition.get("key")): index
        for index, definition in enumerate(definitions)
    }
    keys = (
        "site",
        "hist",
        "behavior",
        "sex_at_birth",
        "discriminator_1",
        "discriminator_2",
        "year_dx",
    )
    result: list[tuple[Any, ...]] = []
    for row in _array(table.get("rows"), "staging table rows"):
        if not isinstance(row, list):
            raise SeerApiError("SEER staging table rows must contain arrays")
        cells = [
            row[index]
            if (index := positions.get(key, -1)) >= 0 and index < len(row)
            else None
            for key in keys
        ]
        result.append((schema.number, *cells))
    return result


def _producer_rows(
    schemas: list[_Schema],
    table_ids: list[str],
    tables: dict[str, dict[str, Any]],
    links: list[tuple[str, str]],
) -> dict[str, list[tuple[Any, ...]]]:
    rows: dict[str, list[tuple[Any, ...]]] = {
        filename: [] for filename in SSDI_CONTRACT
    }
    rows["registry.csv"] = list(STATIC_REGISTRIES)
    seen_schemas: set[str] = set()
    seen_schema_items: set[tuple[str, Any]] = set()
    naaccr_items: dict[int, dict[str, Any]] = {}

    for schema in schemas:
        payload = schema.payload
        if schema.number not in seen_schemas:
            rows["staging_schema.csv"].append(
                (schema.number, payload.get("id"), payload.get("name"))
            )
            seen_schemas.add(schema.number)

        selection_id = payload.get("schema_selection_table")
        selection = (
            tables.get(str(selection_id)) if selection_id not in (None, "") else None
        )
        rows["schema_selection_rule.csv"].extend(_selection_rows(schema, selection))

        inputs = _objects(payload.get("inputs"), "staging schema inputs")
        for item in sorted(
            (item for item in inputs if _is_ssdi(item)), key=_item_sort_key
        ):
            item_number = item.get("naaccr_item")
            table_id = _table_id(item)
            table = tables.get(table_id) if table_id is not None else None
            if item_number not in (None, ""):
                numeric_item = _item_sort_key(item)
                existing = naaccr_items.get(numeric_item)
                if existing is None:
                    naaccr_items[numeric_item] = {
                        "name": item.get("name"),
                        "xml_id": item.get("naaccr_xml_id"),
                        "unit": item.get("unit"),
                        "decimal_places": item.get("decimal_places"),
                    }
                else:
                    if existing["unit"] is None and item.get("unit") is not None:
                        existing["unit"] = item.get("unit")
                    if (
                        existing["decimal_places"] is None
                        and item.get("decimal_places") is not None
                    ):
                        existing["decimal_places"] = item.get("decimal_places")

            key = (schema.number, item_number)
            if key in seen_schema_items:
                continue
            seen_schema_items.add(key)
            rows["schema_item.csv"].append(
                (
                    schema.number,
                    item_number,
                    "input",
                    _bool(item.get("used_for_staging")),
                    item.get("default"),
                    _table_text(table, "description"),
                    _table_text(table, "rationale"),
                    _table_text(table, "additional_info"),
                    _table_text(table, "notes"),
                    _table_text(table, "coding_guidelines"),
                )
            )
            metadata_names = {
                entry.get("name")
                for entry in _objects(item.get("metadata"), "staging input metadata")
            }
            for registry_code in ("SEER", "NPCR", "COC", "CCCR"):
                rows["schema_item_requirement.csv"].append(
                    (
                        schema.number,
                        item_number,
                        registry_code,
                        _bool(f"{registry_code}_REQUIRED" in metadata_names),
                    )
                )
            rows["schema_item_code.csv"].extend(
                _code_rows(schema.number, item_number, table)
            )

        for item in _objects(payload.get("outputs"), "staging schema outputs"):
            item_number = item.get("naaccr_item")
            if not isinstance(item_number, int) or isinstance(item_number, bool):
                continue
            numeric_item = _item_sort_key(item)
            if numeric_item not in naaccr_items:
                naaccr_items[numeric_item] = {
                    "name": item.get("name"),
                    "xml_id": item.get("naaccr_xml_id"),
                    "unit": None,
                    "decimal_places": None,
                }
            key = (schema.number, item_number)
            if key in seen_schema_items:
                continue
            seen_schema_items.add(key)
            table_id = _table_id(item)
            table = tables.get(table_id) if table_id is not None else None
            rows["schema_item.csv"].append(
                (
                    schema.number,
                    item_number,
                    "output",
                    "false",
                    item.get("default"),
                    _table_text(table, "description"),
                    _table_text(table, "rationale"),
                    _table_text(table, "additional_info"),
                    _table_text(table, "notes"),
                    _table_text(table, "coding_guidelines"),
                )
            )
            rows["schema_item_code.csv"].extend(
                _code_rows(schema.number, item_number, table)
            )

    rows["naaccr_item.csv"] = [
        (
            item_number,
            values["name"],
            values["xml_id"],
            values["unit"],
            values["decimal_places"],
        )
        for item_number, values in sorted(naaccr_items.items())
    ]

    for table_id in table_ids:
        table = tables[table_id]
        rows["staging_table.csv"].append(
            (
                table_id,
                table.get("name"),
                table.get("title"),
                table.get("subtitle"),
                table.get("description"),
                table.get("notes"),
                table.get("coding_guidelines"),
            )
        )
        for index, definition in enumerate(
            _objects(table.get("definition"), "staging table definition")
        ):
            rows["staging_table_column.csv"].append(
                (
                    table_id,
                    index,
                    definition.get("key"),
                    definition.get("name"),
                    definition.get("type"),
                    definition.get("source"),
                )
            )
        for index, cells in enumerate(_array(table.get("rows"), "staging table rows")):
            if not isinstance(cells, list):
                raise SeerApiError("SEER staging table rows must contain arrays")
            rows["staging_table_row.csv"].append(
                (
                    table_id,
                    index,
                    json.dumps(cells, ensure_ascii=False, separators=(",", ":")),
                )
            )
    rows["schema_involved_table.csv"] = list(links)
    return rows


def write_ssdi_csvs(
    schemas: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    *,
    table_ids: list[str],
    algorithm: str,
    staging_version: str,
    naaccr_version: str,
    output_dir: Path = DEFAULT_CSV_DIR,
) -> SsdiFetchResult:
    """Derive all twelve SSDI CSVs from already-fetched staging DTOs."""

    ordered_schemas = _sorted_schemas(schemas)
    expected_table_ids, links = _table_and_link_order(ordered_schemas)
    if table_ids != expected_table_ids:
        raise SeerApiError("staging table order does not match the schema payloads")
    table_by_id = _table_map(table_ids, tables)
    rows = _producer_rows(ordered_schemas, table_ids, table_by_id, links)
    for filename, columns in SSDI_CONTRACT.items():
        write_csv(output_dir / filename, columns, rows[filename])
    write_csv(
        output_dir / VERSION_FILE,
        VERSION_COLUMNS,
        [
            (
                algorithm,
                staging_version,
                naaccr_version,
                f"{BASE_URL}/rest/staging/{algorithm}/{staging_version}",
            )
        ],
    )
    return SsdiFetchResult(
        algorithm=algorithm,
        staging_version=staging_version,
        naaccr_version=naaccr_version,
        schema_count=len(rows["staging_schema.csv"]),
        item_count=len(rows["naaccr_item.csv"]),
        table_count=len(rows["staging_table.csv"]),
        involved_table_count=len(rows["schema_involved_table.csv"]),
    )


def fetch_ssdi(
    client: SeerApiClient,
    *,
    naaccr_version: str,
    algorithm: str = "eod_public",
    staging_version: str = "3.3",
    output_dir: Path = DEFAULT_CSV_DIR,
) -> SsdiFetchResult:
    """Validate NAACCR, fetch staging schemas/tables once, and write the CSV set."""

    versions = client.versions()
    if str(naaccr_version) not in {str(entry.get("version")) for entry in versions}:
        raise SeerApiError(f"Version does not exist: {naaccr_version}")
    schemas = client.schemas(algorithm, staging_version)
    ordered_schemas = _sorted_schemas(schemas)
    table_ids, _links = _table_and_link_order(ordered_schemas)
    tables = client.tables(algorithm, staging_version, table_ids)
    return write_ssdi_csvs(
        schemas,
        tables,
        table_ids=table_ids,
        algorithm=algorithm,
        staging_version=staging_version,
        naaccr_version=str(naaccr_version),
        output_dir=output_dir,
    )
