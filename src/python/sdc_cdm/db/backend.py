"""Database backend contract used by the build driver."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any


class DatabaseBackend(ABC):
    dialect: str

    @abstractmethod
    def execute_units(self, units: Sequence[str]) -> None:
        """Execute one manifest file atomically."""

    @abstractmethod
    def execute(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
        *,
        return_scalar: bool = False,
    ) -> Any:
        """Execute and commit one ledger or run-log statement."""

    @abstractmethod
    def fetch_one(self, sql: str, parameters: Sequence[Any] = ()) -> Any:
        """Return one row, or None."""

    @abstractmethod
    def fetch_all(self, sql: str, parameters: Sequence[Any] = ()) -> list[Any]:
        """Return all result rows."""

    @abstractmethod
    def table_exists(self, schema: str, table: str) -> bool:
        """Return whether a table exists."""

    @abstractmethod
    def close(self) -> None:
        """Close the database connection."""

    def __enter__(self) -> "DatabaseBackend":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
