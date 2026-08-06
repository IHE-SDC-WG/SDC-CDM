"""SQLite attached-database backend."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.manifest import SCHEMA_ORDER


def schema_database_path(control_path: Path, schema: str) -> Path:
    """Return the sibling file used for an attached SQLite schema."""

    return control_path.with_name(f"{control_path.stem}.{schema}.db")


class SQLiteBackend(DatabaseBackend):
    dialect = "sqlite"

    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path) if database_path != ":memory:" else None
        if self.database_path is not None:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            data_source = str(self.database_path)
        else:
            data_source = ":memory:"
        self.connection = sqlite3.connect(data_source)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.schema_paths: dict[str, Path | None] = {}
        for schema in SCHEMA_ORDER:
            schema_path = (
                schema_database_path(self.database_path, schema)
                if self.database_path is not None
                else None
            )
            self.schema_paths[schema] = schema_path
            target = str(schema_path) if schema_path is not None else ":memory:"
            self.connection.execute(f'ATTACH DATABASE ? AS "{schema}"', (target,))

    def execute_units(self, units: Sequence[str]) -> None:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            for unit in units:
                self.connection.execute(unit)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def execute(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
        *,
        return_scalar: bool = False,
    ) -> Any:
        try:
            cursor = self.connection.execute(sql, tuple(parameters))
            value = cursor.fetchone()[0] if return_scalar else cursor.lastrowid
            self.connection.commit()
            return value
        except Exception:
            self.connection.rollback()
            raise

    def fetch_one(self, sql: str, parameters: Sequence[Any] = ()) -> Any:
        return self.connection.execute(sql, tuple(parameters)).fetchone()

    def table_exists(self, schema: str, table: str) -> bool:
        row = self.fetch_one(
            f'SELECT 1 FROM "{schema}".sqlite_master WHERE type = ? AND name = ?',
            ("table", table),
        )
        return row is not None

    def close(self) -> None:
        self.connection.close()
