"""Run the manifest's validation scripts and judge every check they report.

Script contract (different from the bridge scripts): every unit returns rows
(check_name, category, actual). The SQL only counts; Python judges. The
structural, provenance, and reconciliation categories pass at zero; coverage
passes at or below its validate_thresholds.csv row; report rows are printed and
never fail. All units run in one transaction, so every count reads one
snapshot, and validation writes nothing but its etl.run row.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sdc_cdm.bridge.runner import DEFAULT_SEED_DIR, BridgeError, check_prerequisites
from sdc_cdm.bridge.seeds import VALIDATE_THRESHOLDS_FILE, read_validate_thresholds
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.manifest import DatabaseManifest, EtlEntry
from sdc_cdm.db.paths import repository_path
from sdc_cdm.db.run_log import RunLog
from sdc_cdm.db.sqlscript import split_script


ZERO_CATEGORIES = ("structural", "provenance", "reconciliation")
CATEGORIES = (*ZERO_CATEGORIES, "coverage", "report")


@dataclass(frozen=True)
class CheckResult:
    name: str
    category: str
    actual: int
    # 0 for a must-be-zero check, the threshold for coverage, None for report
    # rows and for a coverage check with no threshold.
    limit: int | None
    status: str  # PASS, FAIL, or INFO


@dataclass(frozen=True)
class ValidateResult:
    run_id: int
    checks: tuple[CheckResult, ...]
    # One line per failure: a failed check, or a threshold that names no check.
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def _run_checks(backend: DatabaseBackend, entry: EtlEntry) -> list[tuple[str, str, int]]:
    path = repository_path(entry.path)
    rows: list[tuple[str, str, int]] = []
    for unit in split_script(backend.dialect, path.read_text(encoding="utf-8")).executable:
        result = backend.execute_uncommitted_returning(unit)
        if result is None:
            raise BridgeError(f"{entry.path}: a validation unit returned no result set")
        for row in result:
            if len(row) != 3:
                raise BridgeError(
                    f"{entry.path}: a validation row has {len(row)} columns, expected "
                    "check_name, category, actual"
                )
            rows.append((str(row[0]), str(row[1]), int(row[2])))
    return rows


def _judge(
    rows: list[tuple[str, str, int]], thresholds: dict[str, int],
) -> tuple[tuple[CheckResult, ...], tuple[str, ...]]:
    seen: set[str] = set()
    for name, category, _actual in rows:
        if name in seen:
            raise BridgeError(f"validation check {name} is reported more than once")
        if category not in CATEGORIES:
            raise BridgeError(f"validation check {name} has unknown category {category!r}")
        seen.add(name)

    checks: list[CheckResult] = []
    failures: list[str] = []
    for name, category, actual in rows:
        if category == "report":
            checks.append(CheckResult(name, category, actual, None, "INFO"))
            continue
        if category == "coverage":
            limit = thresholds.get(name)
            if limit is None:
                checks.append(CheckResult(name, category, actual, None, "FAIL"))
                failures.append(f"{name}: no row in {VALIDATE_THRESHOLDS_FILE}")
                continue
        else:
            limit = 0
        passed = actual <= limit
        checks.append(CheckResult(name, category, actual, limit, "PASS" if passed else "FAIL"))
        if not passed:
            failures.append(f"{name}: {actual} exceeds {limit}")
    coverage = {name for name, category, _actual in rows if category == "coverage"}
    failures.extend(
        f"{name}: {VALIDATE_THRESHOLDS_FILE} names no coverage check"
        for name in sorted(set(thresholds) - coverage)
    )
    return tuple(checks), tuple(failures)


def run_validate(
    backend: DatabaseBackend,
    manifest: DatabaseManifest,
    *,
    seed_dir: Path = DEFAULT_SEED_DIR,
) -> ValidateResult:
    """Check prerequisites, run every validation entry in one snapshot, and judge."""

    entries = manifest.validate_entries_for(backend.dialect)
    run_log = RunLog(backend)
    run_id = run_log.start("validate")
    try:
        check_prerequisites(backend, entries, seed_dir, command="validate")
        seeds = {seed for entry in entries for seed in entry.seeds}
        thresholds = (
            read_validate_thresholds(seed_dir / VALIDATE_THRESHOLDS_FILE)
            if VALIDATE_THRESHOLDS_FILE in seeds else {}
        )
        rows: list[tuple[str, str, int]] = []
        with backend.transaction():
            for entry in entries:
                rows.extend(_run_checks(backend, entry))
        checks, failures = _judge(rows, thresholds)
    except Exception as exc:
        run_log.finish(run_id, error=str(exc))
        raise
    run_log.finish(
        run_id,
        error="validation failed:\n- " + "\n- ".join(failures) if failures else None,
    )
    return ValidateResult(run_id, checks, failures)
