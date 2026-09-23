"""Implementation of the manifest-driven build command."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.ledger import (
    MigrationDecision,
    MigrationLedger,
    decide_migration,
)
from sdc_cdm.db.manifest import DatabaseManifest, ManifestEntry
from sdc_cdm.db.paths import repository_path
from sdc_cdm.db.run_log import RunLog
from sdc_cdm.db.sqlscript import split_script


class BuildStatus(str, Enum):
    APPLIED = "APPLY"
    SKIPPED = "SKIP"
    REAPPLIED = "REAPPLY"
    HASH_ACCEPTED = "ACCEPT-HASH"
    WOULD_APPLY = "WOULD-APPLY"
    WOULD_REAPPLY = "WOULD-REAPPLY"
    WOULD_ACCEPT_HASH = "WOULD-ACCEPT-HASH"


@dataclass(frozen=True)
class BuildAction:
    path: str
    status: BuildStatus


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BuildRunner:
    _NAACCR_VALUE_DDL = {
        "sqlite": "database/schemas/naaccr/ddl/sqlite/1_naaccr_sqlite_ddl.sql",
        "sqlserver": "database/schemas/naaccr/ddl/sqlserver/1_naaccr_sqlserver_ddl.sql",
    }

    def __init__(
        self,
        manifest: DatabaseManifest,
        backend: DatabaseBackend,
        *,
        accept_changed_hashes: bool = False,
    ):
        self.manifest = manifest
        self.backend = backend
        self.accept_changed_hashes = accept_changed_hashes
        self.ledger = MigrationLedger(backend)
        self.run_log = RunLog(backend)

    def _naaccr_value_shape(self) -> tuple[bool, bool]:
        """Return whether the table has the new column and nullable item number."""
        if not self.backend.table_exists("naaccr", "naaccr_value"):
            return False, False
        if self.backend.dialect == "sqlite":
            columns = {
                row[1]: row[3]
                for row in self.backend.fetch_all("PRAGMA naaccr.table_info(naaccr_value)")
            }
            return "ecp_code" in columns, columns.get("item_num") == 0
        columns = {
            row[0]: row[1]
            for row in self.backend.fetch_all(
                "SELECT COLUMN_NAME, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = 'naaccr' AND TABLE_NAME = 'naaccr_value'"
            )
        }
        return "ecp_code" in columns, columns.get("item_num") == "YES"

    def _legacy_naaccr_value_count(self) -> int | None:
        if not self.backend.table_exists("naaccr", "naaccr_value"):
            return None
        has_ecp_code, nullable_item_num = self._naaccr_value_shape()
        if has_ecp_code and nullable_item_num:
            return None
        return int(self.backend.fetch_one("SELECT COUNT(*) FROM naaccr.naaccr_value")[0])

    @staticmethod
    def _reject_populated_legacy_value(count: int | None) -> None:
        if count:
            raise RuntimeError(
                f"naaccr.naaccr_value has {count} legacy row(s) with ambiguous "
                "identifier systems; recover full CAP OBX-3.1 codes from the original "
                "messages and reload before upgrading"
            )

    def _verify_naaccr_value_shape(self) -> None:
        if self._naaccr_value_shape() != (True, True):
            raise RuntimeError("naaccr.naaccr_value identifier schema is not upgraded")
        if self.backend.dialect == "sqlite":
            row = self.backend.fetch_one(
                "SELECT sql FROM naaccr.sqlite_master WHERE type = 'table' "
                "AND name = 'naaccr_value'"
            )
            valid = row is not None and "ck_naaccr_value_identifier" in row[0].lower()
        else:
            valid = bool(
                self.backend.fetch_one(
                    "SELECT COUNT(*) FROM sys.check_constraints "
                    "WHERE parent_object_id = OBJECT_ID('naaccr.naaccr_value') "
                    "AND name = 'CK_naaccr_value_identifier' "
                    "AND is_disabled = 0 AND is_not_trusted = 0"
                )[0]
            )
        if not valid:
            raise RuntimeError("naaccr.naaccr_value identifier check is missing")

    def _legacy_value_decision(self, entry: ManifestEntry) -> MigrationDecision:
        # An empty legacy table is always rebuilt; whether that is a first apply
        # or a reapply depends only on the ledger, as in any other entry.
        if self.ledger.get(entry.path) is not None:
            return MigrationDecision.REAPPLY
        return MigrationDecision.APPLY

    def _execute_entry(self, entry: ManifestEntry) -> str:
        path = repository_path(entry.path)
        digest = _sha256(path)
        split = split_script(self.backend.dialect, path.read_text(encoding="utf-8"))
        self.backend.execute_units(split.executable)
        return digest

    def _replace_empty_legacy_value(self, entry: ManifestEntry) -> str:
        """Drop and recreate an empty legacy table in one transaction.

        The emptiness check that gates the drop runs under the same lock as the
        drop, so rows a concurrent importer adds after the early check are
        rejected instead of lost. SQLite's BEGIN IMMEDIATE already holds the
        write lock on every attached database; SQL Server takes an exclusive
        table lock that also blocks a concurrent ALTER or DROP until commit.
        """

        path = repository_path(entry.path)
        digest = _sha256(path)
        split = split_script(self.backend.dialect, path.read_text(encoding="utf-8"))
        with self.backend.transaction():
            if self.backend.dialect == "sqlserver":
                self.backend.fetch_one(
                    "SELECT COUNT(*) FROM naaccr.naaccr_value WITH (TABLOCKX, HOLDLOCK)"
                )
            count = self._legacy_naaccr_value_count()
            self._reject_populated_legacy_value(count)
            if count == 0:
                self.backend.execute_uncommitted("DROP TABLE naaccr.naaccr_value")
            for unit in split.executable:
                self.backend.execute_uncommitted(unit)
        return digest

    def _dry_run(self, entries: tuple[ManifestEntry, ...]) -> list[BuildAction]:
        legacy_count = self._legacy_naaccr_value_count()
        self._reject_populated_legacy_value(legacy_count)
        actions: list[BuildAction] = []
        if not self.ledger.exists():
            return [BuildAction(entry.path, BuildStatus.WOULD_APPLY) for entry in entries]
        for entry in entries:
            digest = _sha256(repository_path(entry.path))
            decision = decide_migration(
                self.ledger.get(entry.path),
                digest,
                reapply_on_change=entry.reapply_on_change,
                accept_changed_hashes=self.accept_changed_hashes,
            )
            if (
                entry.path == self._NAACCR_VALUE_DDL[self.backend.dialect]
                and legacy_count == 0
            ):
                decision = self._legacy_value_decision(entry)
            status = {
                MigrationDecision.APPLY: BuildStatus.WOULD_APPLY,
                MigrationDecision.SKIP: BuildStatus.SKIPPED,
                MigrationDecision.REAPPLY: BuildStatus.WOULD_REAPPLY,
                MigrationDecision.ACCEPT_HASH: BuildStatus.WOULD_ACCEPT_HASH,
            }[decision]
            actions.append(BuildAction(entry.path, status))
        return actions

    def run(self, *, dry_run: bool = False) -> list[BuildAction]:
        entries = self.manifest.entries_for(self.backend.dialect)
        if dry_run:
            return self._dry_run(entries)

        legacy_count = self._legacy_naaccr_value_count()
        self._reject_populated_legacy_value(legacy_count)

        self.backend.prepare_for_writes()
        actions: list[BuildAction] = []
        run_id: int | None = None
        start_index = 0
        try:
            if not self.ledger.exists():
                bootstrap = entries[0]
                if bootstrap.schema != "etl":
                    raise RuntimeError("the first build entry must create the etl schema")
                digest = self._execute_entry(bootstrap)
                if not self.ledger.exists():
                    raise RuntimeError("the first build entry did not create etl.schema_migration")
                run_id = self.run_log.start("build")
                self.ledger.record(bootstrap.path, digest, run_id)
                actions.append(BuildAction(bootstrap.path, BuildStatus.APPLIED))
                start_index = 1
            else:
                run_id = self.run_log.start("build")

            for entry in entries[start_index:]:
                path = repository_path(entry.path)
                digest = _sha256(path)
                decision = decide_migration(
                    self.ledger.get(entry.path),
                    digest,
                    reapply_on_change=entry.reapply_on_change,
                    accept_changed_hashes=self.accept_changed_hashes,
                )
                replace_empty_legacy_value = (
                    entry.path == self._NAACCR_VALUE_DDL[self.backend.dialect]
                    and legacy_count == 0
                )
                if replace_empty_legacy_value:
                    # No clinical rows can be lost. The revised DDL creates the new
                    # table and indexes in both dialects.
                    decision = self._legacy_value_decision(entry)
                    legacy_count = None
                if decision is MigrationDecision.SKIP:
                    actions.append(BuildAction(entry.path, BuildStatus.SKIPPED))
                    continue
                if decision is MigrationDecision.ACCEPT_HASH:
                    self.ledger.record(entry.path, digest, run_id)
                    actions.append(BuildAction(entry.path, BuildStatus.HASH_ACCEPTED))
                    continue
                if replace_empty_legacy_value:
                    self._replace_empty_legacy_value(entry)
                else:
                    self._execute_entry(entry)
                self.ledger.record(entry.path, digest, run_id)
                status = (
                    BuildStatus.REAPPLIED
                    if decision is MigrationDecision.REAPPLY
                    else BuildStatus.APPLIED
                )
                actions.append(BuildAction(entry.path, status))
            self._verify_naaccr_value_shape()
            self.run_log.finish(run_id)
            return actions
        except Exception as exc:
            if run_id is not None:
                self.run_log.finish(run_id, error=str(exc))
            raise
