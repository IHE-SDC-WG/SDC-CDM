"""Read one consistent database state across several statements.

Used by validate and export. On SQLite, transaction()'s BEGIN IMMEDIATE keeps
every other writer out until it ends. On SQL Server, default READ COMMITTED
would let a concurrent commit land between statements, so the block runs
SERIALIZABLE: its range locks make concurrent writers wait, and it needs no
database option, unlike SNAPSHOT. The session's previous level is restored.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sdc_cdm.db.backend import DatabaseBackend


# sys.dm_exec_sessions.transaction_isolation_level -> SET TRANSACTION ISOLATION LEVEL
SQLSERVER_ISOLATION_LEVELS = {
    1: "READ UNCOMMITTED", 2: "READ COMMITTED", 3: "REPEATABLE READ",
    4: "SERIALIZABLE", 5: "SNAPSHOT",
}
SQLSERVER_ISOLATION_QUERY = (
    "SELECT transaction_isolation_level FROM sys.dm_exec_sessions WHERE session_id = @@SPID"
)


@contextmanager
def consistent_reads(backend: DatabaseBackend) -> Iterator[None]:
    """Make every read of the enclosed transaction see one database state.

    Enter it outside transaction(): its SET statements commit.
    """
    if backend.dialect != "sqlserver":
        yield
        return
    previous = SQLSERVER_ISOLATION_LEVELS[
        int(backend.fetch_one(SQLSERVER_ISOLATION_QUERY)[0])
    ]
    backend.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    try:
        yield
    finally:
        backend.execute(f"SET TRANSACTION ISOLATION LEVEL {previous}")
