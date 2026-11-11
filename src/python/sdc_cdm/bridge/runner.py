"""Run the manifest's ordered bridge scripts in one data transaction.

The run row in etl.run is written outside that transaction, so a failed run
keeps its status and error text after the rollback. Prerequisites are checked
before the transaction opens, and every missing one is named.

Script contract: a unit that returns a result set is a required-data check.
Each returned row is one first-column message naming an offending source row;
any row fails the run and rolls back every derived change from it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sdc_cdm.bridge.seeds import SEEDS
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import SdcCdmError
from sdc_cdm.db.manifest import DatabaseManifest, EtlEntry
from sdc_cdm.db.paths import repository_path
from sdc_cdm.db.run_log import RunLog
from sdc_cdm.db.sqlscript import split_script
from sdc_cdm.vocab.constants import CONSTANTS_PATH, read_constant_specs


DEFAULT_SEED_DIR = repository_path("database/seed")


class BridgeError(SdcCdmError):
    """A prerequisite is missing or the source data cannot be bridged."""


@dataclass(frozen=True)
class ScriptResult:
    path: str
    row_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class BridgeResult:
    run_id: int
    scripts: tuple[ScriptResult, ...]


def _missing_seeds(entries: tuple[EtlEntry, ...], seed_dir: Path) -> list[str]:
    missing: list[str] = []
    for name in sorted({seed for entry in entries for seed in entry.seeds}):
        path = seed_dir / name
        if name not in SEEDS:
            missing.append(f"seed {name}: the bridge has no reader for it")
        elif not path.is_file():
            missing.append(f"seed {name}: not found at {path}")
        else:
            try:
                SEEDS[name][0](path)
            except ValueError as exc:
                missing.append(f"seed {name}: {exc}")
    return missing


def _missing_constants(backend: DatabaseBackend, entries: tuple[EtlEntry, ...]) -> list[str]:
    tracked = {spec.constant_name: spec for spec in read_constant_specs()}
    resolved = {
        str(row[0]): row
        for row in backend.fetch_all(
            "SELECT c.constant_name, c.concept_id, c.vocabulary_id, c.concept_code, "
            "k.concept_id FROM etl.concept_constant c "
            "LEFT JOIN omop.concept k ON k.concept_id = c.concept_id "
            "AND k.vocabulary_id = c.vocabulary_id AND k.concept_code = c.concept_code "
            "AND k.invalid_reason IS NULL"
        )
    }
    missing: list[str] = []
    for name in sorted({constant for entry in entries for constant in entry.constants}):
        spec = tracked.get(name)
        row = resolved.get(name)
        if spec is None:
            missing.append(f"constant {name}: not tracked in {CONSTANTS_PATH}")
        elif row is None:
            missing.append(
                f"constant {name}: not in etl.concept_constant; "
                "run `sdc-cdm constants resolve`"
            )
        elif (row[2], row[3]) != (spec.vocabulary_id, spec.concept_code):
            missing.append(
                f"constant {name}: resolved from {(row[2], row[3])!r} but "
                f"{CONSTANTS_PATH} tracks {(spec.vocabulary_id, spec.concept_code)!r}; "
                "run `sdc-cdm constants resolve`"
            )
        elif row[4] is None:
            missing.append(
                f"constant {name}: concept {int(row[1])} is not a valid "
                f"{(spec.vocabulary_id, spec.concept_code)!r} concept in the loaded vocabulary"
            )
    return missing


def _missing_database_state(backend: DatabaseBackend) -> list[str]:
    missing: list[str] = []
    version = backend.fetch_one(
        "SELECT vocabulary_version FROM omop.vocabulary WHERE vocabulary_id = 'None'"
    )
    if version is None or not (version[0] or "").strip():
        missing.append(
            "vocabulary version: omop.vocabulary has no 'None' row with a "
            "vocabulary_version; run `sdc-cdm vocab load`"
        )
    elif len(version[0]) > 20:
        missing.append(
            f"vocabulary version: {version[0]!r} is longer than the 20 characters "
            "omop.cdm_source allows"
        )
    built = backend.fetch_one(
        "SELECT b.algorithm, b.dd_version_id, d.is_current "
        "FROM naaccr.concept_map_build_state b "
        "LEFT JOIN naaccr.data_dictionary_version d "
        "ON d.dd_version_id = b.dd_version_id AND d.algorithm = b.algorithm"
    )
    if built is None:
        missing.append(
            "concept map: naaccr.concept_map_build_state is empty; run `sdc-cdm maps build`"
        )
    elif built[2] != 1:
        missing.append(
            f"concept map: built for {built[0]}/{built[1]}, which is not a current "
            "dictionary version; run `sdc-cdm maps build`"
        )
    return missing


def _run_script(backend: DatabaseBackend, entry: EtlEntry) -> ScriptResult:
    path = repository_path(entry.path)
    split = split_script(backend.dialect, path.read_text(encoding="utf-8"))
    for unit in split.executable:
        rows = backend.execute_uncommitted_returning(unit)
        if rows:
            raise BridgeError(
                f"{entry.path}: {len(rows)} source row(s) cannot be bridged:\n- "
                + "\n- ".join(str(row[0]) for row in rows)
            )
    counts = tuple(
        (table, int(backend.fetch_one(f"SELECT COUNT(*) FROM {table}")[0]))
        for table in entry.tables
    )
    return ScriptResult(entry.path, counts)


def run_bridge(
    backend: DatabaseBackend,
    manifest: DatabaseManifest,
    *,
    seed_dir: Path = DEFAULT_SEED_DIR,
) -> BridgeResult:
    """Check prerequisites, then apply every bridge entry in one transaction."""

    entries = manifest.bridge_entries_for(backend.dialect)
    run_log = RunLog(backend)
    run_id = run_log.start("bridge")
    try:
        missing = [
            *_missing_seeds(entries, seed_dir),
            *_missing_constants(backend, entries),
            *_missing_database_state(backend),
        ]
        if missing:
            raise BridgeError(
                "bridge prerequisites are missing; nothing was written:\n- "
                + "\n- ".join(missing)
            )
        with backend.transaction():
            for name in sorted({seed for entry in entries for seed in entry.seeds}):
                SEEDS[name][1](backend, seed_dir / name)
            scripts = tuple(_run_script(backend, entry) for entry in entries)
        run_log.finish(run_id)
        return BridgeResult(run_id, scripts)
    except Exception as exc:
        run_log.finish(run_id, error=str(exc))
        raise
