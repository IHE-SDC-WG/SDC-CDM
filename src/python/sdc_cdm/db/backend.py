"""Database backend contract used by the build driver."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any


def _batched(
    rows: Iterable[Sequence[Any]], batch_size: int
) -> Iterator[list[Sequence[Any]]]:
    """Yield lists of at most batch_size rows without materializing the input."""

    batch: list[Sequence[Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


class DatabaseBackend(ABC):
    dialect: str
    connection: Any
    _in_transaction = False

    def prepare_for_writes(self) -> None:
        """Create any structure the manifest itself cannot create.

        Called only when the driver is about to write, so a dry run leaves the
        target untouched.
        """

    @abstractmethod
    def qualified_name(self, schema: str, table: str) -> str:
        """Return one quoted, schema-qualified table name."""

    def _begin(self) -> None:
        """Open the transaction that transaction() commits or rolls back.

        Nothing to do by default: pyodbc connects with autocommit off, so SQL
        Server already holds one open and transaction() adopts it, including
        whatever db.bulk.suspend_constraints issued just before.
        """

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Run one block as one transaction.

        The only copy of the begin/commit/rollback flow. execute() and
        execute_units() commit, so both refuse to run inside this block;
        bulk_insert, execute_uncommitted, fetch_one and fetch_all do not commit
        and are the supported ways to work inside it.
        """

        if self._in_transaction:
            raise RuntimeError(
                "transaction() is already active and does not nest: neither "
                "dialect can give a nested block its own commit"
            )
        self._begin()
        self._in_transaction = True
        try:
            yield
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise
        finally:
            self._in_transaction = False

    def _reject_during_transaction(self, operation: str) -> None:
        if self._in_transaction:
            raise RuntimeError(
                f"{operation}() commits, so it cannot run inside transaction(); "
                "write with bulk_insert or execute_uncommitted and read with "
                "fetch_one or fetch_all"
            )

    def execute_uncommitted(
        self, sql: str, parameters: Sequence[Any] = ()
    ) -> None:
        """Execute one row-less statement without committing.

        The write path that is legal inside transaction(). Constraint DDL and
        pragmas go through here so a pre-commit rejection still rolls the whole
        block back.
        """

        self.connection.cursor().execute(sql, tuple(parameters))

    def _bulk_cursor(self) -> Any:
        """Return the one cursor bulk_insert reuses for every batch."""

        return self.connection.cursor()

    def bulk_insert(
        self,
        schema: str,
        table: str,
        columns: Sequence[str],
        rows: Iterable[Sequence[Any]],
        *,
        batch_size: int = 10_000,
    ) -> int:
        """Insert rows in batches and return how many were sent.

        Streams: rows may be a generator and only one batch is held at a time.
        Never commits; wrap the call in transaction() so validation can still
        roll the load back.
        """

        if not columns:
            raise ValueError(
                f"bulk_insert into {schema}.{table} needs at least one column"
            )
        if batch_size < 1:
            raise ValueError(f"batch_size must be positive, got {batch_size}")
        left, right = ('"', '"') if self.dialect == "sqlite" else ("[", "]")
        quoted = ", ".join(f"{left}{column}{right}" for column in columns)
        markers = ", ".join("?" for _ in columns)
        sql = (
            f"INSERT INTO {self.qualified_name(schema, table)} "
            f"({quoted}) VALUES ({markers})"
        )
        cursor = self._bulk_cursor()
        inserted = 0
        for batch in _batched(rows, batch_size):
            cursor.executemany(sql, batch)
            inserted += len(batch)
        return inserted

    @abstractmethod
    def execute_units(self, units: Sequence[str]) -> None:
        """Execute one manifest file atomically; reject inside transaction()."""

    @abstractmethod
    def execute(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
        *,
        return_scalar: bool = False,
    ) -> Any:
        """Execute and commit one statement; reject inside transaction()."""

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
