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

    def _execute_entry(self, entry: ManifestEntry) -> str:
        path = repository_path(entry.path)
        digest = _sha256(path)
        split = split_script(self.backend.dialect, path.read_text(encoding="utf-8"))
        self.backend.execute_units(split.executable)
        return digest

    def _dry_run(self, entries: tuple[ManifestEntry, ...]) -> list[BuildAction]:
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
                if decision is MigrationDecision.SKIP:
                    actions.append(BuildAction(entry.path, BuildStatus.SKIPPED))
                    continue
                if decision is MigrationDecision.ACCEPT_HASH:
                    self.ledger.record(entry.path, digest, run_id)
                    actions.append(BuildAction(entry.path, BuildStatus.HASH_ACCEPTED))
                    continue
                self._execute_entry(entry)
                self.ledger.record(entry.path, digest, run_id)
                status = (
                    BuildStatus.REAPPLIED
                    if decision is MigrationDecision.REAPPLY
                    else BuildStatus.APPLIED
                )
                actions.append(BuildAction(entry.path, status))
            self.run_log.finish(run_id)
            return actions
        except Exception as exc:
            if run_id is not None:
                self.run_log.finish(run_id, error=str(exc))
            raise
