"""Applied-migration ledger and hash-change policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import MigrationHashMismatch


class MigrationDecision(str, Enum):
    APPLY = "apply"
    SKIP = "skip"
    REAPPLY = "reapply"
    ACCEPT_HASH = "accept-hash"


@dataclass(frozen=True)
class MigrationRecord:
    migration_path: str
    file_sha256: str
    previous_sha256: str | None


def decide_migration(
    record: MigrationRecord | None,
    file_sha256: str,
    *,
    reapply_on_change: bool,
    accept_changed_hashes: bool,
) -> MigrationDecision:
    if record is None:
        return MigrationDecision.APPLY
    if record.file_sha256 == file_sha256:
        return MigrationDecision.SKIP
    if accept_changed_hashes:
        return MigrationDecision.ACCEPT_HASH
    if reapply_on_change:
        return MigrationDecision.REAPPLY
    raise MigrationHashMismatch(
        f"applied migration changed: {record.migration_path} "
        f"(ledger {record.file_sha256}, file {file_sha256}); "
        "rerun with --accept-changed-hashes to accept without executing it"
    )


class MigrationLedger:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    def exists(self) -> bool:
        return self.backend.table_exists("etl", "schema_migration")

    def get(self, migration_path: str) -> MigrationRecord | None:
        if not self.exists():
            return None
        row = self.backend.fetch_one(
            "SELECT migration_path, file_sha256, previous_sha256 "
            "FROM etl.schema_migration WHERE migration_path = ?",
            (migration_path,),
        )
        return MigrationRecord(*row) if row is not None else None

    def record(self, migration_path: str, file_sha256: str, run_id: int) -> None:
        current = self.get(migration_path)
        now = (
            "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
            if self.backend.dialect == "sqlite"
            else "SYSUTCDATETIME()"
        )
        if current is None:
            self.backend.execute(
                "INSERT INTO etl.schema_migration "
                "(migration_path, file_sha256, previous_sha256, applied_at, last_run_id) "
                f"VALUES (?, ?, NULL, {now}, ?)",
                (migration_path, file_sha256, run_id),
            )
        else:
            self.backend.execute(
                "UPDATE etl.schema_migration "
                "SET previous_sha256 = file_sha256, file_sha256 = ?, "
                f"applied_at = {now}, last_run_id = ? WHERE migration_path = ?",
                (file_sha256, run_id, migration_path),
            )
