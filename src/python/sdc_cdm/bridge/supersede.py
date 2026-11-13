"""Refresh bridge-owned rows atomically with explicit report supersession."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sdc_cdm.bridge.runner import DEFAULT_SEED_DIR, apply_entries, check_prerequisites
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.manifest import DatabaseManifest
from sdc_cdm.db.run_log import RunLog
from sdc_cdm.reports.versions import Supersession, supersede_in_transaction


@dataclass(frozen=True)
class SupersessionResult:
    run_id: int
    supersession: Supersession
    bridge_refreshed: bool


def supersede_and_refresh(
    backend: DatabaseBackend,
    manifest: DatabaseManifest,
    predecessor_id: int,
    successor_id: int,
    *,
    seed_dir: Path = DEFAULT_SEED_DIR,
) -> SupersessionResult:
    """Move selection, refreshing the full bridge only for an already bridged group.

    The run log survives rollback. Unbridged groups need no bridge prerequisites.
    A full refresh also bridges pending loads and recalculates observation periods.
    """
    log = RunLog(backend)
    run_id = log.start("supersede")
    try:
        with backend.transaction():
            selection = supersede_in_transaction(backend, predecessor_id, successor_id)
            refreshed = backend.fetch_one(
                "SELECT 1 FROM sdc.note_report WHERE report_group_id = ?",
                (selection.report_group_id,),
            ) is not None
            if refreshed:
                entries = manifest.bridge_entries_for(backend.dialect)
                check_prerequisites(backend, entries, seed_dir)
                apply_entries(backend, entries, seed_dir)
        log.finish(run_id)
        return SupersessionResult(run_id, selection, refreshed)
    except Exception as exc:
        log.finish(run_id, error=str(exc))
        raise
