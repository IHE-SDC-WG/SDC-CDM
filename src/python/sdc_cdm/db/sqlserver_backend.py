"""SQL Server backend loaded only when that dialect is selected."""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Any

from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.manifest import SCHEMA_ORDER


class SqlServerBackend(DatabaseBackend):
    dialect = "sqlserver"

    def __init__(self, connection_string: str):
        try:
            pyodbc = importlib.import_module("pyodbc")
        except ImportError as exc:
            raise RuntimeError(
                "SQL Server builds require the optional pyodbc dependency"
            ) from exc
        self.connection = pyodbc.connect(connection_string, autocommit=False)

    def prepare_for_writes(self) -> None:
        self._ensure_schemas()

    def _ensure_schemas(self) -> None:
        for schema in SCHEMA_ORDER:
            cursor = self.connection.cursor()
            cursor.execute(
                f"IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = '{schema}') "
                f"EXEC('CREATE SCHEMA {schema}')"
            )
            self.connection.commit()

    def execute_units(self, units: Sequence[str]) -> None:
        try:
            cursor = self.connection.cursor()
            for unit in units:
                cursor.execute(unit)
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
            cursor = self.connection.cursor()
            cursor.execute(sql, tuple(parameters))
            value = cursor.fetchone()[0] if return_scalar else None
            self.connection.commit()
            return value
        except Exception:
            self.connection.rollback()
            raise

    def fetch_one(self, sql: str, parameters: Sequence[Any] = ()) -> Any:
        cursor = self.connection.cursor()
        cursor.execute(sql, tuple(parameters))
        return cursor.fetchone()

    def fetch_all(self, sql: str, parameters: Sequence[Any] = ()) -> list[Any]:
        cursor = self.connection.cursor()
        cursor.execute(sql, tuple(parameters))
        return list(cursor.fetchall())

    def table_exists(self, schema: str, table: str) -> bool:
        return self.fetch_one("SELECT OBJECT_ID(?, 'U')", (f"{schema}.{table}",))[0] is not None

    def close(self) -> None:
        self.connection.close()
