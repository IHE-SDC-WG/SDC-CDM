"""Transactional NAACCR dictionary and SSDI CSV loader for both dialects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.bulk import suspend_constraints, verify_constraints
from sdc_cdm.db.errors import VocabularyError
from sdc_cdm.naaccr.columns import (
    ALLOWED_CODE_COLUMNS,
    ALLOWED_CODE_FILE,
    DICTIONARY_COLUMNS,
    DICTIONARY_FILE,
    REGISTRY_REQUIREMENT_COLUMNS,
    REGISTRY_REQUIREMENT_FILE,
    SSDI_VERSION_FILE,
    VERSION_COLUMNS,
    VERSION_FILE,
)
from sdc_cdm.naaccr.csv_io import DEFAULT_CSV_DIR, read_csv, read_single_row
from sdc_cdm.naaccr.ssdi import (
    REGISTRY_COLUMNS,
    SCHEMA_INVOLVED_TABLE_COLUMNS,
    SCHEMA_ITEM_CODE_COLUMNS,
    SCHEMA_ITEM_COLUMNS,
    SELECTION_RULE_COLUMNS,
    SSDI_CONTRACT,
    SSDI_FILES,
    SSDI_ITEM_COLUMNS,
    STAGING_SCHEMA_COLUMNS,
    STAGING_TABLE_COLUMN_COLUMNS,
    STAGING_TABLE_COLUMNS,
    STAGING_TABLE_ROW_COLUMNS,
    STATIC_REGISTRIES,
)

VERSIONED_DELETE_ORDER = (
    "schema_involved_table",
    "schema_item_code",
    "schema_item_requirement",
    "schema_item",
    "schema_selection_rule",
    "staging_table_row",
    "staging_table_column",
    "staging_table",
    "naaccr_item_allowed_code",
    "naaccr_item_registry_requirement",
    "naaccr_item",
    "staging_schema",
)

# Used by the structural regression test. Each child must appear before every
# parent in VERSIONED_DELETE_ORDER. data_dictionary_version and registry rows
# are retained across reloads, so they are not in the delete list.
VERSIONED_FOREIGN_KEYS = {
    "schema_involved_table": ("staging_schema", "staging_table"),
    "schema_item_code": ("schema_item",),
    "schema_item_requirement": ("schema_item",),
    "schema_item": ("staging_schema", "naaccr_item"),
    "schema_selection_rule": ("staging_schema",),
    "staging_table_row": ("staging_table",),
    "staging_table_column": ("staging_table",),
    "naaccr_item_allowed_code": ("naaccr_item",),
    "naaccr_item_registry_requirement": ("naaccr_item",),
}

CONSTRAINT_TABLES = (
    "data_dictionary_version",
    "staging_schema",
    "schema_selection_rule",
    "naaccr_item",
    "naaccr_item_allowed_code",
    "naaccr_item_registry_requirement",
    "schema_item",
    "registry",
    "schema_item_requirement",
    "schema_item_code",
    "staging_table",
    "staging_table_column",
    "staging_table_row",
    "schema_involved_table",
)

EXPECTED_ITEM_COLUMNS = frozenset(
    (
        "dd_version_id",
        "item_num",
        "name",
        "xml_id",
        "unit",
        "decimal_places",
        "data_type",
        "length",
        "padding",
        "alignment",
        "trim",
        "section",
        "parent_xml_element",
    )
    + DICTIONARY_COLUMNS[7:]
)


@dataclass(frozen=True)
class LoadResult:
    dd_version_id: int
    algorithm: str
    version: str
    row_counts: dict[str, int]
    stub_item_count: int
    stub_item_nums: tuple[int, ...]


@dataclass(frozen=True)
class _Sources:
    version: dict[str, str]
    dictionary: list[dict[str, str]]
    allowed_codes: list[dict[str, str]]
    registry_requirements: list[dict[str, str]]
    ssdi: dict[str, list[dict[str, str]]]


def _required_int(row: dict[str, str], column: str, filename: str) -> int:
    value = row[column]
    if not value:
        raise VocabularyError(f"{filename} has an empty required {column}")
    try:
        return int(value)
    except ValueError as exc:
        raise VocabularyError(
            f"{filename} has invalid integer {column}={value!r}"
        ) from exc


def _optional_int(row: dict[str, str], column: str, filename: str) -> int | None:
    if not row[column]:
        return None
    return _required_int(row, column, filename)


def _optional(row: dict[str, str], column: str) -> str | None:
    return row[column] or None


def _required_text(row: dict[str, str], column: str, filename: str) -> str:
    value = row[column]
    if not value:
        raise VocabularyError(f"{filename} has an empty required {column}")
    return value


def _boolean(row: dict[str, str], column: str, filename: str) -> int:
    value = row[column].lower()
    if value in {"1", "true"}:
        return 1
    if value in {"0", "false"}:
        return 0
    raise VocabularyError(f"{filename} has invalid boolean {column}={row[column]!r}")


def _preflight_target(backend: DatabaseBackend) -> None:
    if not backend.table_exists("naaccr", "naaccr_item"):
        raise VocabularyError(
            "rebuild required: naaccr.naaccr_item does not exist; re-run build"
        )
    if backend.dialect == "sqlite":
        actual = {
            str(row[1])
            for row in backend.fetch_all('PRAGMA "naaccr".table_info("naaccr_item")')
        }
    else:
        actual = {
            column
            for column in EXPECTED_ITEM_COLUMNS
            if backend.fetch_one(
                "SELECT COL_LENGTH('naaccr.NAACCR_ITEM', ?)", (column,)
            )[0]
            is not None
        }
    missing = sorted(EXPECTED_ITEM_COLUMNS - actual)
    if not missing:
        return
    if backend.dialect == "sqlite":
        control_path = getattr(backend, "database_path", None)
        target = (
            str(control_path) if control_path is not None else "the SQLite database"
        )
        action = (
            f"delete {target} and its sibling schema database files, then re-run build"
        )
    else:
        action = "re-run build so the guarded dictionary DDL is reapplied"
    raise VocabularyError(
        "rebuild required: naaccr.naaccr_item is missing columns "
        f"{', '.join(missing)}; {action}"
    )


def _read_sources(csv_dir: Path) -> _Sources:
    version = read_single_row(csv_dir, VERSION_FILE, VERSION_COLUMNS)
    dictionary = read_csv(csv_dir, DICTIONARY_FILE, DICTIONARY_COLUMNS)
    allowed_codes = read_csv(csv_dir, ALLOWED_CODE_FILE, ALLOWED_CODE_COLUMNS)
    registry_requirements = read_csv(
        csv_dir,
        REGISTRY_REQUIREMENT_FILE,
        REGISTRY_REQUIREMENT_COLUMNS,
    )
    if not dictionary:
        raise VocabularyError(f"{csv_dir / DICTIONARY_FILE} has no rows")

    present_ssdi = {
        filename for filename in SSDI_FILES if (csv_dir / filename).is_file()
    }
    if present_ssdi and len(present_ssdi) != len(SSDI_FILES):
        missing = sorted(set(SSDI_FILES) - present_ssdi)
        raise VocabularyError("incomplete SSDI CSV set; missing: " + ", ".join(missing))
    if present_ssdi:
        _require_same_generation(
            version, read_single_row(csv_dir, SSDI_VERSION_FILE, VERSION_COLUMNS)
        )
    ssdi = (
        {
            filename: read_csv(csv_dir, filename, columns)
            for filename, columns in SSDI_CONTRACT.items()
        }
        if present_ssdi
        else {}
    )
    _preflight_schema_items(dictionary, ssdi.get("schema_item.csv", []))
    return _Sources(
        version=version,
        dictionary=dictionary,
        allowed_codes=allowed_codes,
        registry_requirements=registry_requirements,
        ssdi=ssdi,
    )


def _generation(row: dict[str, str]) -> tuple[str, str, str]:
    return (row["algorithm"], row["version"], row["naaccr_version"])


def _describe_generation(row: dict[str, str]) -> str:
    return f"{row['algorithm']}/{row['version']} (NAACCR {row['naaccr_version']})"


def _require_same_generation(
    dictionary_row: dict[str, str], ssdi_row: dict[str, str]
) -> None:
    """Reject a directory whose dictionary and SSDI stamps disagree."""

    if _generation(dictionary_row) == _generation(ssdi_row):
        return
    raise VocabularyError(
        f"{SSDI_VERSION_FILE} generation {_describe_generation(ssdi_row)} does not "
        f"match {VERSION_FILE} generation {_describe_generation(dictionary_row)}; "
        "re-run dict fetch and ssdi fetch with the same --algorithm, "
        "--staging-version, and NAACCR version"
    )


def _preflight_schema_items(
    dictionary: list[dict[str, str]], schema_items: list[dict[str, str]]
) -> None:
    dictionary_nums = {
        _required_int(row, "item_num", DICTIONARY_FILE) for row in dictionary
    }
    schema_nums = {
        _required_int(row, "item_num", "schema_item.csv") for row in schema_items
    }
    missing = sorted(schema_nums - dictionary_nums)
    if missing:
        sample = ", ".join(str(item_num) for item_num in missing[:10])
        raise VocabularyError(
            f"schema_item.csv has {len(missing)} item_num(s) missing from "
            f"{DICTIONARY_FILE}; first: {sample}"
        )


def _resolve_version(backend: DatabaseBackend, row: dict[str, str]) -> int:
    algorithm = _required_text(row, "algorithm", VERSION_FILE)
    version = _required_text(row, "version", VERSION_FILE)
    naaccr_version = _optional(row, "naaccr_version")
    source_api = _optional(row, "source_api")
    table = backend.qualified_name("naaccr", "data_dictionary_version")
    if backend.dialect == "sqlite":
        backend.execute_uncommitted(
            f"INSERT INTO {table} "
            "(algorithm, version, naaccr_version, source_api, is_current) "
            "VALUES (?, ?, ?, ?, 0) "
            "ON CONFLICT(algorithm, version) DO NOTHING",
            (algorithm, version, naaccr_version, source_api),
        )
        existing = backend.fetch_one(
            f"SELECT dd_version_id FROM {table} WHERE algorithm = ? AND version = ?",
            (algorithm, version),
        )
    else:
        existing = backend.fetch_one(
            f"SELECT dd_version_id FROM {table} WITH (UPDLOCK, HOLDLOCK) "
            "WHERE algorithm = ? AND version = ?",
            (algorithm, version),
        )
        if existing is None:
            existing = backend.fetch_one(
                f"INSERT INTO {table} "
                "(algorithm, version, naaccr_version, source_api, is_current) "
                "OUTPUT INSERTED.dd_version_id VALUES (?, ?, ?, ?, 0)",
                (algorithm, version, naaccr_version, source_api),
            )
    if existing is None:
        raise VocabularyError(
            f"could not resolve data_dictionary_version for {algorithm}/{version}"
        )
    dd_version_id = int(existing[0])
    backend.execute_uncommitted(
        f"UPDATE {table} SET naaccr_version = ?, source_api = ? "
        "WHERE dd_version_id = ?",
        (naaccr_version, source_api, dd_version_id),
    )
    # Clear first so the filtered unique index remains satisfied, then promote
    # this generation. Both statements roll back with the rest of the load.
    backend.execute_uncommitted(
        f"UPDATE {table} SET is_current = 0 WHERE algorithm = ? AND dd_version_id <> ?",
        (algorithm, dd_version_id),
    )
    backend.execute_uncommitted(
        f"UPDATE {table} SET is_current = 1 WHERE dd_version_id = ?",
        (dd_version_id,),
    )
    return dd_version_id


def _clear_version(backend: DatabaseBackend, dd_version_id: int) -> None:
    for table in VERSIONED_DELETE_ORDER:
        backend.execute_uncommitted(
            f"DELETE FROM {backend.qualified_name('naaccr', table)} "
            "WHERE dd_version_id = ?",
            (dd_version_id,),
        )


def _seed_registries(
    backend: DatabaseBackend, csv_rows: list[dict[str, str]]
) -> dict[str, int]:
    requested = {code: name for code, name in STATIC_REGISTRIES}
    for row in csv_rows:
        requested[_required_text(row, "code", "registry.csv")] = _required_text(
            row, "name", "registry.csv"
        )
    table = backend.qualified_name("naaccr", "registry")
    existing = {
        str(row[1]): (int(row[0]), str(row[2]))
        for row in backend.fetch_all(f"SELECT id, code, name FROM {table}")
    }
    missing: list[tuple[str, str]] = []
    for code, name in requested.items():
        if code not in existing:
            missing.append((code, name))
        elif existing[code][1] != name:
            backend.execute_uncommitted(
                f"UPDATE {table} SET name = ? WHERE code = ?", (name, code)
            )
    if missing:
        backend.bulk_insert("naaccr", "registry", REGISTRY_COLUMNS, missing)
    return {
        str(row[1]): int(row[0])
        for row in backend.fetch_all(f"SELECT id, code FROM {table}")
        if str(row[1]) in requested
    }


def _dictionary_tuples(
    rows: list[dict[str, str]], dd_version_id: int
) -> list[tuple[Any, ...]]:
    integer_columns = {"item_num", "length", "year_implemented", "year_retired"}
    result: list[tuple[Any, ...]] = []
    for row in rows:
        values: list[Any] = [dd_version_id]
        for column in DICTIONARY_COLUMNS:
            if column == "item_num":
                values.append(_required_int(row, column, DICTIONARY_FILE))
            elif column in integer_columns:
                values.append(_optional_int(row, column, DICTIONARY_FILE))
            else:
                values.append(_optional(row, column))
        result.append(tuple(values))
    return result


def _apply_ssdi_item_metadata(
    backend: DatabaseBackend,
    dd_version_id: int,
    rows: list[dict[str, str]],
    dictionary_nums: set[int],
) -> tuple[int, ...]:
    table = backend.qualified_name("naaccr", "naaccr_item")
    stubs: list[tuple[Any, ...]] = []
    stub_nums: list[int] = []
    for row in rows:
        item_num = _required_int(row, "item_num", "naaccr_item.csv")
        decimal_places = _optional_int(row, "decimal_places", "naaccr_item.csv")
        unit = _optional(row, "unit")
        if item_num in dictionary_nums:
            backend.execute_uncommitted(
                f"UPDATE {table} SET unit = ?, decimal_places = ? "
                "WHERE dd_version_id = ? AND item_num = ?",
                (unit, decimal_places, dd_version_id, item_num),
            )
            continue
        stub_nums.append(item_num)
        stubs.append(
            (
                dd_version_id,
                item_num,
                _optional(row, "name"),
                _optional(row, "xml_id"),
                unit,
                decimal_places,
            )
        )
    if stubs:
        backend.bulk_insert(
            "naaccr",
            "naaccr_item",
            ("dd_version_id",) + SSDI_ITEM_COLUMNS,
            stubs,
        )
    return tuple(sorted(stub_nums))


def _insert_ssdi(
    backend: DatabaseBackend,
    dd_version_id: int,
    rows: dict[str, list[dict[str, str]]],
    registry_ids: dict[str, int],
    counts: dict[str, int],
) -> None:
    def bulk(
        table: str,
        columns: tuple[str, ...],
        values: list[tuple[Any, ...]],
    ) -> None:
        counts[table] = backend.bulk_insert(
            "naaccr", table, ("dd_version_id",) + columns, values
        )

    bulk(
        "staging_schema",
        STAGING_SCHEMA_COLUMNS,
        [
            (
                dd_version_id,
                _required_text(row, "schema_id_number", "staging_schema.csv"),
                _required_text(row, "schema_id", "staging_schema.csv"),
                _optional(row, "schema_name"),
            )
            for row in rows["staging_schema.csv"]
        ],
    )
    bulk(
        "staging_table",
        STAGING_TABLE_COLUMNS,
        [
            (dd_version_id,)
            + tuple(
                _required_text(row, column, "staging_table.csv")
                if column == "table_key"
                else _optional(row, column)
                for column in STAGING_TABLE_COLUMNS
            )
            for row in rows["staging_table.csv"]
        ],
    )
    bulk(
        "staging_table_column",
        STAGING_TABLE_COLUMN_COLUMNS,
        [
            (
                dd_version_id,
                _required_text(row, "table_key", "staging_table_column.csv"),
                _required_int(row, "col_index", "staging_table_column.csv"),
                _optional(row, "col_key"),
                _optional(row, "col_name"),
                _optional(row, "col_type"),
                _optional(row, "col_source"),
            )
            for row in rows["staging_table_column.csv"]
        ],
    )
    bulk(
        "staging_table_row",
        STAGING_TABLE_ROW_COLUMNS,
        [
            (
                dd_version_id,
                _required_text(row, "table_key", "staging_table_row.csv"),
                _required_int(row, "row_index", "staging_table_row.csv"),
                _optional(row, "cells"),
            )
            for row in rows["staging_table_row.csv"]
        ],
    )
    bulk(
        "schema_selection_rule",
        SELECTION_RULE_COLUMNS,
        [
            (dd_version_id,)
            + tuple(
                _required_text(row, column, "schema_selection_rule.csv")
                if column == "schema_id_number"
                else _optional(row, column)
                for column in SELECTION_RULE_COLUMNS
            )
            for row in rows["schema_selection_rule.csv"]
        ],
    )
    bulk(
        "schema_item",
        SCHEMA_ITEM_COLUMNS,
        [
            (
                dd_version_id,
                _required_text(row, "schema_id_number", "schema_item.csv"),
                _required_int(row, "item_num", "schema_item.csv"),
                _required_text(row, "item_role", "schema_item.csv"),
                _boolean(row, "used_for_staging", "schema_item.csv"),
                _optional(row, "default_value"),
                _optional(row, "description"),
                _optional(row, "rationale"),
                _optional(row, "additional_info"),
                _optional(row, "table_notes"),
                _optional(row, "coding_guidelines"),
            )
            for row in rows["schema_item.csv"]
        ],
    )
    requirement_values: list[tuple[Any, ...]] = []
    for row in rows["schema_item_requirement.csv"]:
        code = _required_text(row, "registry_code", "schema_item_requirement.csv")
        if code not in registry_ids:
            raise VocabularyError(
                f"schema_item_requirement.csv registry code not found: {code}"
            )
        requirement_values.append(
            (
                dd_version_id,
                _required_text(row, "schema_id_number", "schema_item_requirement.csv"),
                _required_int(row, "item_num", "schema_item_requirement.csv"),
                registry_ids[code],
                _boolean(row, "is_required", "schema_item_requirement.csv"),
            )
        )
    counts["schema_item_requirement"] = backend.bulk_insert(
        "naaccr",
        "schema_item_requirement",
        (
            "dd_version_id",
            "schema_id_number",
            "item_num",
            "registry_id",
            "is_required",
        ),
        requirement_values,
    )
    bulk(
        "schema_item_code",
        SCHEMA_ITEM_CODE_COLUMNS,
        [
            (
                dd_version_id,
                _required_text(row, "schema_id_number", "schema_item_code.csv"),
                _required_int(row, "item_num", "schema_item_code.csv"),
                _required_text(row, "code", "schema_item_code.csv"),
                _optional(row, "description"),
            )
            for row in rows["schema_item_code.csv"]
        ],
    )
    bulk(
        "schema_involved_table",
        SCHEMA_INVOLVED_TABLE_COLUMNS,
        [
            (
                dd_version_id,
                _required_text(row, "schema_id_number", "schema_involved_table.csv"),
                _required_text(row, "table_key", "schema_involved_table.csv"),
            )
            for row in rows["schema_involved_table.csv"]
        ],
    )


def _orphan_count(backend: DatabaseBackend, dd_version_id: int) -> int:
    schema_item = backend.qualified_name("naaccr", "schema_item")
    item = backend.qualified_name("naaccr", "naaccr_item")
    return int(
        backend.fetch_one(
            f"SELECT COUNT(*) FROM {schema_item} si "
            f"LEFT JOIN {item} ni "
            "ON ni.dd_version_id = si.dd_version_id AND ni.item_num = si.item_num "
            "WHERE si.dd_version_id = ? AND ni.item_num IS NULL",
            (dd_version_id,),
        )[0]
    )


def load_dictionary(
    backend: DatabaseBackend,
    *,
    csv_dir: Path = DEFAULT_CSV_DIR,
) -> LoadResult:
    """Replace one dictionary generation atomically from one agreeing CSV set."""

    _preflight_target(backend)
    sources = _read_sources(csv_dir)
    dictionary_nums = {
        _required_int(row, "item_num", DICTIONARY_FILE) for row in sources.dictionary
    }
    counts: dict[str, int] = {}
    stub_nums: tuple[int, ...] = ()
    try:
        with (
            suspend_constraints(backend, "naaccr", CONSTRAINT_TABLES),
            backend.transaction(),
        ):
            dd_version_id = _resolve_version(backend, sources.version)
            _clear_version(backend, dd_version_id)
            registry_rows = sources.ssdi.get("registry.csv", [])
            registry_ids = _seed_registries(backend, registry_rows)
            counts["registry"] = len(registry_ids)

            item_values = _dictionary_tuples(sources.dictionary, dd_version_id)
            counts["naaccr_item"] = backend.bulk_insert(
                "naaccr",
                "naaccr_item",
                ("dd_version_id",) + DICTIONARY_COLUMNS,
                item_values,
            )
            if sources.ssdi:
                stub_nums = _apply_ssdi_item_metadata(
                    backend,
                    dd_version_id,
                    sources.ssdi["naaccr_item.csv"],
                    dictionary_nums,
                )
                counts["naaccr_item"] += len(stub_nums)

            counts["naaccr_item_allowed_code"] = backend.bulk_insert(
                "naaccr",
                "naaccr_item_allowed_code",
                ("dd_version_id",) + ALLOWED_CODE_COLUMNS,
                [
                    (
                        dd_version_id,
                        _required_int(row, "item_num", ALLOWED_CODE_FILE),
                        _required_int(row, "code_seq", ALLOWED_CODE_FILE),
                        _required_text(row, "code", ALLOWED_CODE_FILE),
                        _optional(row, "description"),
                    )
                    for row in sources.allowed_codes
                ],
            )
            counts["naaccr_item_registry_requirement"] = backend.bulk_insert(
                "naaccr",
                "naaccr_item_registry_requirement",
                ("dd_version_id",) + REGISTRY_REQUIREMENT_COLUMNS,
                [
                    (
                        dd_version_id,
                        _required_int(row, "item_num", REGISTRY_REQUIREMENT_FILE),
                        _required_text(row, "registry_code", REGISTRY_REQUIREMENT_FILE),
                        _required_text(
                            row, "collect_status", REGISTRY_REQUIREMENT_FILE
                        ),
                    )
                    for row in sources.registry_requirements
                ],
            )
            if sources.ssdi:
                _insert_ssdi(
                    backend,
                    dd_version_id,
                    sources.ssdi,
                    registry_ids,
                    counts,
                )

            orphan_count = _orphan_count(backend, dd_version_id)
            if orphan_count:
                raise VocabularyError(
                    f"loaded generation has {orphan_count} orphan schema_item row(s)"
                )
            verify_constraints(backend, "naaccr", CONSTRAINT_TABLES)
    except VocabularyError:
        raise
    except Exception as exc:
        raise VocabularyError(f"NAACCR dictionary load failed: {exc}") from exc

    return LoadResult(
        dd_version_id=dd_version_id,
        algorithm=sources.version["algorithm"],
        version=sources.version["version"],
        row_counts=counts,
        stub_item_count=len(stub_nums),
        stub_item_nums=stub_nums,
    )
