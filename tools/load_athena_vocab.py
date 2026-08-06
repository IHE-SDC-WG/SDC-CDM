#!/usr/bin/env python3
"""Load an OHDSI Athena vocabulary extract into OMOP CDM 5.4 tables."""

from __future__ import annotations

import argparse
import csv
import importlib
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


class LoaderError(RuntimeError):
    """Raised when an Athena extract or database target is not safe to load."""


@dataclass(frozen=True)
class TableSpec:
    file_name: str
    table_name: str
    columns: tuple[str, ...]
    kinds: tuple[str, ...]


@dataclass(frozen=True)
class LoadReport:
    row_counts: dict[str, int]
    vocabulary_versions: tuple[tuple[str, str | None], ...]


TABLE_SPECS = (
    TableSpec(
        "DOMAIN.csv",
        "domain",
        ("domain_id", "domain_name", "domain_concept_id"),
        ("text", "text", "integer"),
    ),
    TableSpec(
        "VOCABULARY.csv",
        "vocabulary",
        (
            "vocabulary_id",
            "vocabulary_name",
            "vocabulary_reference",
            "vocabulary_version",
            "vocabulary_concept_id",
        ),
        ("text", "text", "text", "text", "integer"),
    ),
    TableSpec(
        "CONCEPT_CLASS.csv",
        "concept_class",
        (
            "concept_class_id",
            "concept_class_name",
            "concept_class_concept_id",
        ),
        ("text", "text", "integer"),
    ),
    TableSpec(
        "RELATIONSHIP.csv",
        "relationship",
        (
            "relationship_id",
            "relationship_name",
            "is_hierarchical",
            "defines_ancestry",
            "reverse_relationship_id",
            "relationship_concept_id",
        ),
        ("text", "text", "text", "text", "text", "integer"),
    ),
    TableSpec(
        "CONCEPT.csv",
        "concept",
        (
            "concept_id",
            "concept_name",
            "domain_id",
            "vocabulary_id",
            "concept_class_id",
            "standard_concept",
            "concept_code",
            "valid_start_date",
            "valid_end_date",
            "invalid_reason",
        ),
        (
            "integer",
            "text",
            "text",
            "text",
            "text",
            "text",
            "text",
            "date",
            "date",
            "text",
        ),
    ),
    TableSpec(
        "CONCEPT_RELATIONSHIP.csv",
        "concept_relationship",
        (
            "concept_id_1",
            "concept_id_2",
            "relationship_id",
            "valid_start_date",
            "valid_end_date",
            "invalid_reason",
        ),
        ("integer", "integer", "text", "date", "date", "text"),
    ),
    TableSpec(
        "CONCEPT_SYNONYM.csv",
        "concept_synonym",
        ("concept_id", "concept_synonym_name", "language_concept_id"),
        ("integer", "text", "integer"),
    ),
    TableSpec(
        "CONCEPT_ANCESTOR.csv",
        "concept_ancestor",
        (
            "ancestor_concept_id",
            "descendant_concept_id",
            "min_levels_of_separation",
            "max_levels_of_separation",
        ),
        ("integer", "integer", "integer", "integer"),
    ),
    TableSpec(
        "DRUG_STRENGTH.csv",
        "drug_strength",
        (
            "drug_concept_id",
            "ingredient_concept_id",
            "amount_value",
            "amount_unit_concept_id",
            "numerator_value",
            "numerator_unit_concept_id",
            "denominator_value",
            "denominator_unit_concept_id",
            "box_size",
            "valid_start_date",
            "valid_end_date",
            "invalid_reason",
        ),
        (
            "integer",
            "integer",
            "decimal",
            "integer",
            "decimal",
            "integer",
            "decimal",
            "integer",
            "integer",
            "date",
            "date",
            "text",
        ),
    ),
)

EXPECTED_HEADERS = {
    spec.file_name: tuple(column.upper() for column in spec.columns)
    for spec in TABLE_SPECS
}

# Older databases may contain only these seed concepts so the bridge can run
# without a full vocabulary. A fresh Athena load replaces them with canonical rows.
SQLITE_ESSENTIAL_SEED_IDS = frozenset(
    {0, 8507, 8532, 32817, 32856, 32879, 45905771, 1147289}
)
BRIDGE_REQUIRED_CONCEPT_IDS = frozenset({0, 32817, 32879, 1147289})
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _require_identifier(value: str, label: str) -> str:
    if not IDENTIFIER_RE.fullmatch(value):
        raise LoaderError(f"Invalid {label}: {value!r}")
    return value


def _parse_date(value: str, file_name: str, line_number: int) -> date:
    for format_string in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, format_string).date()
        except ValueError:
            pass
    raise LoaderError(
        f"{file_name}:{line_number}: invalid date {value!r}; "
        "expected YYYYMMDD or YYYY-MM-DD"
    )


def _convert_value(
    value: str, kind: str, file_name: str, line_number: int
) -> Any:
    if value == "":
        return None
    if kind == "text":
        return value
    if kind == "integer":
        try:
            return int(value)
        except ValueError as exc:
            raise LoaderError(
                f"{file_name}:{line_number}: invalid integer {value!r}"
            ) from exc
    if kind == "decimal":
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise LoaderError(
                f"{file_name}:{line_number}: invalid decimal {value!r}"
            ) from exc
    if kind == "date":
        return _parse_date(value, file_name, line_number)
    raise AssertionError(f"Unsupported field kind: {kind}")


def _read_header(path: Path, delimiter: str) -> tuple[str, ...]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter, quotechar='"')
            header = next(reader)
    except StopIteration as exc:
        raise LoaderError(f"{path.name}: file is empty") from exc
    except UnicodeDecodeError as exc:
        raise LoaderError(f"{path.name}: file is not valid UTF-8") from exc
    return tuple(value.strip().upper() for value in header)


def validate_source_files(
    vocab_dir: Path, delimiter: str
) -> dict[str, Path]:
    if not vocab_dir.is_dir():
        raise LoaderError(f"Vocabulary directory does not exist: {vocab_dir}")

    paths: dict[str, Path] = {}
    errors: list[str] = []
    for spec in TABLE_SPECS:
        path = vocab_dir / spec.file_name
        if not path.is_file():
            errors.append(f"missing {spec.file_name}")
            continue
        actual_header = _read_header(path, delimiter)
        expected_header = EXPECTED_HEADERS[spec.file_name]
        if actual_header != expected_header:
            errors.append(
                f"{spec.file_name} header mismatch\n"
                f"  expected: {delimiter.join(expected_header)}\n"
                f"  actual:   {delimiter.join(actual_header)}"
            )
            continue
        paths[spec.table_name] = path

    if errors:
        raise LoaderError(
            "Athena extract preflight failed:\n- " + "\n- ".join(errors)
        )
    return paths


def iter_table_rows(
    spec: TableSpec, path: Path, delimiter: str
) -> Iterator[tuple[Any, ...]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter, quotechar='"')
        next(reader)
        for line_number, raw_row in enumerate(reader, start=2):
            if not raw_row or all(value == "" for value in raw_row):
                continue
            if len(raw_row) != len(spec.columns):
                raise LoaderError(
                    f"{path.name}:{line_number}: expected {len(spec.columns)} "
                    f"fields, found {len(raw_row)}"
                )
            yield tuple(
                _convert_value(value, kind, path.name, line_number)
                for value, kind in zip(raw_row, spec.kinds)
            )


def inspect_extract(
    vocab_dir: Path, delimiter: str
) -> dict[str, int]:
    paths = validate_source_files(vocab_dir, delimiter)
    counts: dict[str, int] = {}
    for spec in TABLE_SPECS:
        counts[spec.table_name] = sum(
            1 for _ in iter_table_rows(spec, paths[spec.table_name], delimiter)
        )
    return counts


def _batched(
    rows: Iterable[tuple[Any, ...]], batch_size: int
) -> Iterator[list[tuple[Any, ...]]]:
    batch: list[tuple[Any, ...]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


class DatabaseBackend:
    parameter_marker = "?"

    def __init__(self, schema: str, batch_size: int):
        self.schema = _require_identifier(schema, "schema")
        self.batch_size = batch_size
        self.connection: Any = None

    def qualified_table(self, table_name: str) -> str:
        raise NotImplementedError

    def connect(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()

    def ensure_tables_exist(self) -> None:
        raise NotImplementedError

    def begin_load(self) -> None:
        raise NotImplementedError

    def enable_constraints_for_validation(self) -> None:
        raise NotImplementedError

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def reset_after_transaction(self) -> None:
        pass

    def execute(
        self, sql: str, parameters: Sequence[Any] | None = None
    ) -> Any:
        cursor = self.connection.cursor()
        cursor.execute(sql, parameters or ())
        return cursor

    def fetch_scalar(
        self, sql: str, parameters: Sequence[Any] | None = None
    ) -> Any:
        cursor = self.execute(sql, parameters)
        row = cursor.fetchone()
        return None if row is None else row[0]

    def fetch_all(
        self, sql: str, parameters: Sequence[Any] | None = None
    ) -> list[tuple[Any, ...]]:
        cursor = self.execute(sql, parameters)
        return [tuple(row) for row in cursor.fetchall()]

    def insert_rows(
        self, spec: TableSpec, rows: Iterable[tuple[Any, ...]]
    ) -> int:
        placeholders = ", ".join(
            self.parameter_marker for _ in spec.columns
        )
        columns = ", ".join(self.quote_identifier(c) for c in spec.columns)
        sql = (
            f"INSERT INTO {self.qualified_table(spec.table_name)} "
            f"({columns}) VALUES ({placeholders})"
        )
        count = 0
        cursor = self.connection.cursor()
        self.prepare_bulk_cursor(cursor)
        adapted_rows = (self.adapt_row(row) for row in rows)
        for batch in _batched(adapted_rows, self.batch_size):
            cursor.executemany(sql, batch)
            count += len(batch)
        return count

    def adapt_row(self, row: tuple[Any, ...]) -> tuple[Any, ...]:
        return row

    def prepare_bulk_cursor(self, cursor: Any) -> None:
        pass

    def quote_identifier(self, identifier: str) -> str:
        return f'"{_require_identifier(identifier, "column")}"'

    def foreign_key_violations(self) -> list[tuple[Any, ...]]:
        return []


class SqliteBackend(DatabaseBackend):
    def __init__(self, database_path: Path, batch_size: int):
        super().__init__("main", batch_size)
        self.database_path = database_path

    def qualified_table(self, table_name: str) -> str:
        return self.quote_identifier(table_name)

    def connect(self) -> None:
        if not self.database_path.is_file():
            raise LoaderError(
                f"SQLite OMOP database does not exist: {self.database_path}"
            )
        self.connection = sqlite3.connect(
            self.database_path, isolation_level=None
        )

    def ensure_tables_exist(self) -> None:
        missing = []
        for spec in TABLE_SPECS:
            found = self.fetch_scalar(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND lower(name) = lower(?)
                """,
                (spec.table_name,),
            )
            if found is None:
                missing.append(spec.table_name)
        if missing:
            raise LoaderError(
                "SQLite target is missing OMOP vocabulary tables: "
                + ", ".join(missing)
            )

    def begin_load(self) -> None:
        self.connection.execute("PRAGMA foreign_keys = OFF")
        self.connection.execute("BEGIN IMMEDIATE")

    def enable_constraints_for_validation(self) -> None:
        # SQLite cannot change foreign_keys inside a transaction. Explicit
        # orphan queries and foreign_key_check run before the commit.
        pass

    def reset_after_transaction(self) -> None:
        self.connection.execute("PRAGMA foreign_keys = ON")

    def foreign_key_violations(self) -> list[tuple[Any, ...]]:
        return self.fetch_all("PRAGMA foreign_key_check")

    def adapt_row(self, row: tuple[Any, ...]) -> tuple[Any, ...]:
        return tuple(
            value.isoformat()
            if isinstance(value, date)
            else str(value)
            if isinstance(value, Decimal)
            else value
            for value in row
        )


class SqlServerBackend(DatabaseBackend):
    def __init__(self, connection_string: str, schema: str, batch_size: int):
        super().__init__(schema, batch_size)
        self.connection_string = connection_string

    def qualified_table(self, table_name: str) -> str:
        return f"[{self.schema}].[{table_name}]"

    def quote_identifier(self, identifier: str) -> str:
        return f"[{_require_identifier(identifier, 'column')}]"

    def connect(self) -> None:
        try:
            pyodbc = importlib.import_module("pyodbc")
        except ImportError as exc:
            raise LoaderError(
                "SQL Server loading requires pyodbc, a system ODBC manager, "
                "and a SQL Server ODBC driver. Install the platform ODBC "
                "prerequisites and `tools/requirements-vocab.txt`."
            ) from exc
        self.connection = pyodbc.connect(
            self.connection_string, autocommit=False
        )

    def ensure_tables_exist(self) -> None:
        missing = []
        for spec in TABLE_SPECS:
            found = self.fetch_scalar(
                """
                SELECT 1
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
                """,
                (self.schema, spec.table_name),
            )
            if found is None:
                missing.append(spec.table_name)
        if missing:
            raise LoaderError(
                "SQL Server target is missing OMOP vocabulary tables: "
                + ", ".join(missing)
            )

    def begin_load(self) -> None:
        for spec in TABLE_SPECS:
            self.execute(
                f"ALTER TABLE {self.qualified_table(spec.table_name)} "
                "NOCHECK CONSTRAINT ALL"
            )

    def enable_constraints_for_validation(self) -> None:
        for spec in TABLE_SPECS:
            self.execute(
                f"ALTER TABLE {self.qualified_table(spec.table_name)} "
                "WITH CHECK CHECK CONSTRAINT ALL"
            )

    def prepare_bulk_cursor(self, cursor: Any) -> None:
        cursor.fast_executemany = True


def _target_row_counts(backend: DatabaseBackend) -> dict[str, int]:
    return {
        spec.table_name: int(
            backend.fetch_scalar(
                f"SELECT COUNT(*) FROM {backend.qualified_table(spec.table_name)}"
            )
        )
        for spec in TABLE_SPECS
    }


def _prepare_fresh_target(backend: DatabaseBackend) -> None:
    counts = _target_row_counts(backend)
    non_concept_rows = {
        table: count
        for table, count in counts.items()
        if table != "concept" and count
    }
    if non_concept_rows:
        details = ", ".join(
            f"{table}={count}"
            for table, count in sorted(non_concept_rows.items())
        )
        raise LoaderError(
            "Vocabulary target is not fresh. Existing rows were found: "
            f"{details}. Create a fresh OMOP schema for the initial Athena load."
        )

    concept_table = backend.qualified_table("concept")
    existing_ids = {
        int(row[0])
        for row in backend.fetch_all(
            f"SELECT concept_id FROM {concept_table}"
        )
    }
    unexpected_ids = existing_ids - SQLITE_ESSENTIAL_SEED_IDS
    if unexpected_ids:
        sample = ", ".join(str(value) for value in sorted(unexpected_ids)[:10])
        suffix = "..." if len(unexpected_ids) > 10 else ""
        raise LoaderError(
            "Vocabulary target is not fresh. Unexpected concept IDs were "
            f"found: {sample}{suffix}"
        )

    if existing_ids:
        markers = ", ".join(
            backend.parameter_marker for _ in existing_ids
        )
        backend.execute(
            f"DELETE FROM {concept_table} WHERE concept_id IN ({markers})",
            tuple(sorted(existing_ids)),
        )


def _integrity_queries(backend: DatabaseBackend) -> tuple[tuple[str, str], ...]:
    table = backend.qualified_table
    return (
        (
            "concept.domain_id",
            f"""
            SELECT COUNT(*)
            FROM {table('concept')} c
            LEFT JOIN {table('domain')} d ON d.domain_id = c.domain_id
            WHERE d.domain_id IS NULL
            """,
        ),
        (
            "concept.vocabulary_id",
            f"""
            SELECT COUNT(*)
            FROM {table('concept')} c
            LEFT JOIN {table('vocabulary')} v
              ON v.vocabulary_id = c.vocabulary_id
            WHERE v.vocabulary_id IS NULL
            """,
        ),
        (
            "concept.concept_class_id",
            f"""
            SELECT COUNT(*)
            FROM {table('concept')} c
            LEFT JOIN {table('concept_class')} cc
              ON cc.concept_class_id = c.concept_class_id
            WHERE cc.concept_class_id IS NULL
            """,
        ),
        (
            "vocabulary.vocabulary_concept_id",
            f"""
            SELECT COUNT(*)
            FROM {table('vocabulary')} v
            LEFT JOIN {table('concept')} c
              ON c.concept_id = v.vocabulary_concept_id
            WHERE c.concept_id IS NULL
            """,
        ),
        (
            "domain.domain_concept_id",
            f"""
            SELECT COUNT(*)
            FROM {table('domain')} d
            LEFT JOIN {table('concept')} c
              ON c.concept_id = d.domain_concept_id
            WHERE c.concept_id IS NULL
            """,
        ),
        (
            "concept_class.concept_class_concept_id",
            f"""
            SELECT COUNT(*)
            FROM {table('concept_class')} cc
            LEFT JOIN {table('concept')} c
              ON c.concept_id = cc.concept_class_concept_id
            WHERE c.concept_id IS NULL
            """,
        ),
        (
            "relationship.reverse_relationship_id",
            f"""
            SELECT COUNT(*)
            FROM {table('relationship')} r
            LEFT JOIN {table('relationship')} reverse_r
              ON reverse_r.relationship_id = r.reverse_relationship_id
            WHERE reverse_r.relationship_id IS NULL
            """,
        ),
        (
            "relationship.relationship_concept_id",
            f"""
            SELECT COUNT(*)
            FROM {table('relationship')} r
            LEFT JOIN {table('concept')} c
              ON c.concept_id = r.relationship_concept_id
            WHERE c.concept_id IS NULL
            """,
        ),
        (
            "concept_relationship references",
            f"""
            SELECT COUNT(*)
            FROM {table('concept_relationship')} cr
            LEFT JOIN {table('concept')} c1
              ON c1.concept_id = cr.concept_id_1
            LEFT JOIN {table('concept')} c2
              ON c2.concept_id = cr.concept_id_2
            LEFT JOIN {table('relationship')} r
              ON r.relationship_id = cr.relationship_id
            WHERE c1.concept_id IS NULL
               OR c2.concept_id IS NULL
               OR r.relationship_id IS NULL
            """,
        ),
        (
            "concept_synonym references",
            f"""
            SELECT COUNT(*)
            FROM {table('concept_synonym')} cs
            LEFT JOIN {table('concept')} c
              ON c.concept_id = cs.concept_id
            LEFT JOIN {table('concept')} language_c
              ON language_c.concept_id = cs.language_concept_id
            WHERE c.concept_id IS NULL OR language_c.concept_id IS NULL
            """,
        ),
        (
            "concept_ancestor references",
            f"""
            SELECT COUNT(*)
            FROM {table('concept_ancestor')} ca
            LEFT JOIN {table('concept')} ancestor_c
              ON ancestor_c.concept_id = ca.ancestor_concept_id
            LEFT JOIN {table('concept')} descendant_c
              ON descendant_c.concept_id = ca.descendant_concept_id
            WHERE ancestor_c.concept_id IS NULL
               OR descendant_c.concept_id IS NULL
            """,
        ),
        (
            "drug_strength required references",
            f"""
            SELECT COUNT(*)
            FROM {table('drug_strength')} ds
            LEFT JOIN {table('concept')} drug_c
              ON drug_c.concept_id = ds.drug_concept_id
            LEFT JOIN {table('concept')} ingredient_c
              ON ingredient_c.concept_id = ds.ingredient_concept_id
            WHERE drug_c.concept_id IS NULL
               OR ingredient_c.concept_id IS NULL
            """,
        ),
        (
            "drug_strength unit references",
            f"""
            SELECT COUNT(*)
            FROM {table('drug_strength')} ds
            LEFT JOIN {table('concept')} amount_c
              ON amount_c.concept_id = ds.amount_unit_concept_id
            LEFT JOIN {table('concept')} numerator_c
              ON numerator_c.concept_id = ds.numerator_unit_concept_id
            LEFT JOIN {table('concept')} denominator_c
              ON denominator_c.concept_id = ds.denominator_unit_concept_id
            WHERE (ds.amount_unit_concept_id IS NOT NULL
                   AND amount_c.concept_id IS NULL)
               OR (ds.numerator_unit_concept_id IS NOT NULL
                   AND numerator_c.concept_id IS NULL)
               OR (ds.denominator_unit_concept_id IS NOT NULL
                   AND denominator_c.concept_id IS NULL)
            """,
        ),
    )


def _validate_loaded_data(
    backend: DatabaseBackend, expected_counts: dict[str, int]
) -> None:
    actual_counts = _target_row_counts(backend)
    count_errors = [
        f"{table}: file={expected_counts[table]}, database={actual_counts[table]}"
        for table in expected_counts
        if expected_counts[table] != actual_counts[table]
    ]
    if count_errors:
        raise LoaderError(
            "Vocabulary row-count validation failed:\n- "
            + "\n- ".join(count_errors)
        )

    missing_bridge_ids = [
        concept_id
        for concept_id in sorted(BRIDGE_REQUIRED_CONCEPT_IDS)
        if backend.fetch_scalar(
            f"SELECT COUNT(*) FROM {backend.qualified_table('concept')} "
            f"WHERE concept_id = {backend.parameter_marker}",
            (concept_id,),
        )
        == 0
    ]
    if missing_bridge_ids:
        raise LoaderError(
            "Athena extract does not contain concepts required by the "
            "NAACCR-to-OMOP bridge: "
            + ", ".join(str(value) for value in missing_bridge_ids)
        )

    orphan_errors = []
    for label, sql in _integrity_queries(backend):
        count = int(backend.fetch_scalar(sql))
        if count:
            orphan_errors.append(f"{label}: {count}")
    foreign_key_rows = backend.foreign_key_violations()
    if foreign_key_rows:
        orphan_errors.append(
            f"database foreign-key check: {len(foreign_key_rows)}"
        )
    if orphan_errors:
        raise LoaderError(
            "Vocabulary integrity validation failed:\n- "
            + "\n- ".join(orphan_errors)
        )


def load_vocab(
    backend: DatabaseBackend, vocab_dir: Path, delimiter: str
) -> LoadReport:
    paths = validate_source_files(vocab_dir, delimiter)
    backend.connect()
    try:
        backend.ensure_tables_exist()
        backend.begin_load()
        try:
            _prepare_fresh_target(backend)
            row_counts: dict[str, int] = {}
            for spec in TABLE_SPECS:
                row_counts[spec.table_name] = backend.insert_rows(
                    spec,
                    iter_table_rows(
                        spec, paths[spec.table_name], delimiter
                    ),
                )

            backend.enable_constraints_for_validation()
            _validate_loaded_data(backend, row_counts)
            versions = tuple(
                (
                    str(row[0]),
                    None if row[1] is None else str(row[1]),
                )
                for row in backend.fetch_all(
                    f"SELECT vocabulary_id, vocabulary_version "
                    f"FROM {backend.qualified_table('vocabulary')} "
                    "ORDER BY vocabulary_id"
                )
            )
            backend.commit()
        except Exception:
            backend.rollback()
            raise
        finally:
            backend.reset_after_transaction()
    finally:
        backend.close()
    return LoadReport(row_counts=row_counts, vocabulary_versions=versions)


def _build_backend(args: argparse.Namespace) -> DatabaseBackend:
    if args.batch_size <= 0:
        raise LoaderError("--batch-size must be greater than zero")

    if args.dialect == "sqlite":
        if not args.sqlite_db:
            raise LoaderError("--sqlite-db is required for SQLite")
        return SqliteBackend(Path(args.sqlite_db), args.batch_size)

    if args.dialect == "sqlserver":
        connection_string = os.environ.get(
            "ATHENA_SQLSERVER_CONNECTION_STRING"
        )
        if not connection_string:
            raise LoaderError(
                "Set ATHENA_SQLSERVER_CONNECTION_STRING before loading "
                "SQL Server"
            )
        return SqlServerBackend(
            connection_string, args.schema, args.batch_size
        )

    raise LoaderError("--dialect is required unless --check-only is used")


def _delimiter_value(name: str) -> str:
    return "\t" if name == "tab" else ","


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load the nine standard Athena CSV files into a fresh OMOP "
            "CDM 5.4 vocabulary schema."
        )
    )
    parser.add_argument(
        "--dialect",
        choices=("sqlite", "sqlserver"),
        help="Target database dialect",
    )
    parser.add_argument(
        "--vocab-dir",
        default="database/vocab",
        help="Directory containing the extracted Athena files",
    )
    parser.add_argument(
        "--schema",
        default="omop",
        help="OMOP schema for SQL Server (default: omop)",
    )
    parser.add_argument(
        "--sqlite-db",
        help="Path to the SQLite OMOP database file",
    )
    parser.add_argument(
        "--delimiter",
        choices=("tab", "comma"),
        default="tab",
        help="Extract delimiter (default: tab)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
        help="Rows per SQLite or SQL Server batch (default: 10000)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate and count the extract without connecting to a database",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    vocab_dir = Path(args.vocab_dir)
    delimiter = _delimiter_value(args.delimiter)
    try:
        if args.check_only:
            counts = inspect_extract(vocab_dir, delimiter)
            print("Athena extract is valid.")
            for spec in TABLE_SPECS:
                print(f"  {spec.file_name}: {counts[spec.table_name]} rows")
            return 0

        backend = _build_backend(args)
        report = load_vocab(backend, vocab_dir, delimiter)
    except LoaderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: vocabulary load failed: {exc}", file=sys.stderr)
        return 1

    print("Athena vocabulary load completed.")
    for spec in TABLE_SPECS:
        print(
            f"  {spec.table_name}: "
            f"{report.row_counts[spec.table_name]} rows"
        )
    print("Loaded vocabulary versions:")
    for vocabulary_id, version in report.vocabulary_versions:
        print(f"  {vocabulary_id}: {version or '(not supplied)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
