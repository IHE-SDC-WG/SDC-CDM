"""Bulk-load constraint helpers.

Loaders must enter suspend_constraints outside transaction(), use exactly one
transaction() per suspend body, perform inserts and verify_constraints inside
it, and let the outer context restore SQLite enforcement only after the inner
block commits or rolls back.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import VocabularyError


_NOCHECK = "NOCHECK CONSTRAINT ALL"
_WITH_CHECK = "WITH CHECK CHECK CONSTRAINT ALL"
_RESTORE_FAILED = (
    "PRAGMA foreign_keys is still off after suspend_constraints; SQLite "
    "ignored the restore because a transaction is still open"
)


@contextmanager
def suspend_constraints(
    backend: DatabaseBackend, schema: str, tables: Sequence[str]
) -> Iterator[None]:
    """Suspend constraint enforcement for the body, then restore it.

    Enter this outside transaction(): SQLite ignores the pragma inside one and
    cannot restore it inside one either. On SQL Server the NOCHECK DDL is
    uncommitted, so it joins the transaction that transaction() adopts and a rollback
    undoes it with the rows.
    """

    if backend.dialect == "sqlite":
        _sqlite_suspend(backend)
    else:
        _sqlserver_suspend(backend, schema, tables)
    try:
        yield
    except BaseException:
        # Abandon anything the body left open so SQLite can restore enforcement
        # and no SQL Server NOCHECK can be committed by later failure logging.
        backend.rollback()
        if backend.dialect == "sqlite":
            _sqlite_restore(backend)
        raise
    if backend.dialect == "sqlite" and not _sqlite_restore(backend):
        raise VocabularyError(_RESTORE_FAILED)


def verify_constraints(
    backend: DatabaseBackend, schema: str, tables: Sequence[str]
) -> None:
    """Re-check constraints before the caller commits; raise on violations."""

    if backend.dialect == "sqlite":
        violations = constraint_violations(backend, schema)
        if violations:
            raise VocabularyError(
                f"{len(violations)} foreign key violation(s) in schema {schema}; "
                f"first: {violations[0]}"
            )
        return
    for table in tables:
        _alter_constraints(backend, schema, table, _WITH_CHECK)


def constraint_violations(
    backend: DatabaseBackend, schema: str
) -> list[tuple[Any, ...]]:
    """Return the database's own violation rows for one schema."""

    if backend.dialect != "sqlite":
        return []
    return [
        tuple(row)
        for row in backend.fetch_all(f'PRAGMA "{schema}".foreign_key_check')
    ]


def _sqlite_suspend(backend: DatabaseBackend) -> None:
    """Turn SQLite enforcement off and fail if the pragma was ignored."""

    backend.execute_uncommitted("PRAGMA foreign_keys = OFF")
    row = backend.fetch_one("PRAGMA foreign_keys")
    if row is None or int(row[0]) != 0:
        raise VocabularyError(
            "PRAGMA foreign_keys = OFF did not take effect: SQLite ignores it "
            "inside a transaction. Commit or roll back before calling "
            "suspend_constraints, and never call it inside transaction()."
        )


def _sqlite_restore(backend: DatabaseBackend) -> bool:
    """Restore SQLite enforcement without raising on a caller's error path."""

    try:
        backend.execute_uncommitted("PRAGMA foreign_keys = ON")
        row = backend.fetch_one("PRAGMA foreign_keys")
        return row is not None and int(row[0]) == 1
    except Exception:
        return False


def _sqlserver_suspend(
    backend: DatabaseBackend, schema: str, tables: Sequence[str]
) -> None:
    """Apply NOCHECK and roll back if a later table cannot be suspended."""

    try:
        for table in tables:
            _alter_constraints(backend, schema, table, _NOCHECK)
    except BaseException:
        backend.rollback()
        raise


def _alter_constraints(
    backend: DatabaseBackend, schema: str, table: str, clause: str
) -> None:
    qualified = backend.qualified_name(schema, table)
    try:
        backend.execute_uncommitted(f"ALTER TABLE {qualified} {clause}")
    except Exception as exc:
        raise VocabularyError(
            f"ALTER TABLE {qualified} {clause} failed: {exc}"
        ) from exc
