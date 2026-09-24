from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from sdc_cdm.cli.build import BuildAction, BuildRunner, BuildStatus
from sdc_cdm.cli.main import main, registered_commands
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.paths import repository_path
from sdc_cdm.db.sqlite_backend import SQLiteBackend, schema_database_path
from sdc_cdm.db.sqlscript import split_script
from sdc_cdm.db.sqlserver_backend import SqlServerBackend


def _run_build(control_path: Path, *, dry_run: bool = False):
    with SQLiteBackend(control_path) as backend:
        return BuildRunner(load_manifest(), backend).run(dry_run=dry_run)


def test_expected_commands_are_registered() -> None:
    assert registered_commands() == (
        "build",
        "dict fetch",
        "dict load",
        "dict verify",
        "ssdi fetch",
        "vocab load",
        "vocab check",
        "constants resolve",
        "maps build",
        "maps coverage",
        "intake ingest",
        "intake load",
    )
    with pytest.raises(SystemExit) as exc_info:
        main(["ingest"])
    assert exc_info.value.code == 2


@pytest.mark.parametrize(
    ("dialect", "message"),
    (("sqlite", "requires --db"), ("sqlserver", "requires --connection-string")),
)
def test_database_targets_have_no_implicit_connection_details(
    dialect: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SDC_CDM_SQLSERVER_CONNECTION_STRING", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main(["build", "--dialect", dialect])
    assert exc_info.value.code == 2
    assert message in capsys.readouterr().err


def test_list_does_not_require_a_database(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["build", "--dialect", "sqlite", "--list"]) == 0
    output = capsys.readouterr().out
    assert "01 etl" in output
    assert "database/schemas/sdc/ddl/sqlite/1_sdc_sqlite_ddl.sql" in output


def test_build_twice_is_a_no_op(tmp_path: Path) -> None:
    control_path = tmp_path / "build.db"
    first = _run_build(control_path)
    second = _run_build(control_path)

    assert all(action.status is BuildStatus.APPLIED for action in first)
    assert all(action.status is BuildStatus.SKIPPED for action in second)

    with SQLiteBackend(control_path) as backend:
        migration_count = backend.fetch_one("SELECT COUNT(*) FROM etl.schema_migration")[0]
        run_count = backend.fetch_one("SELECT COUNT(*) FROM etl.run")[0]
        assert migration_count == len(load_manifest().entries_for("sqlite"))
        assert run_count == 2
        assert backend.table_exists("intake", "inbound_message")
        assert backend.table_exists("intake", "inbound_envelope")
        assert backend.table_exists("omop", "measurement")
        assert backend.table_exists("naaccr", "naaccr_value")
        assert backend.table_exists("sdc", "sdc_report")


@contextmanager
def _backend(dialect: str, tmp_path: Path) -> Iterator[DatabaseBackend]:
    if dialect == "sqlite":
        backend: DatabaseBackend = SQLiteBackend(tmp_path / "legacy.db")
    else:
        connection_string = os.environ.get("SDC_CDM_SQLSERVER_CONNECTION_STRING")
        if not connection_string:
            pytest.skip("SDC_CDM_SQLSERVER_CONNECTION_STRING is not set")
        backend = SqlServerBackend(connection_string)
    try:
        yield backend
    finally:
        backend.close()


_LEGACY_VALUE_DDL = {
    "sqlite": (
        "CREATE TABLE naaccr.naaccr_value ("
        "naaccr_value_id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL, "
        "episode_key TEXT NOT NULL, item_num INTEGER NOT NULL)"
    ),
    "sqlserver": (
        "CREATE TABLE naaccr.naaccr_value ("
        "naaccr_value_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY, "
        "person_id INT NOT NULL, episode_key NVARCHAR(100) NOT NULL, "
        "item_num INT NOT NULL)"
    ),
}

_INSERT_LEGACY_ROW = (
    "INSERT INTO naaccr.naaccr_value (person_id, episode_key, item_num) "
    "VALUES (1, 'legacy', 2118)"
)


@contextmanager
def _legacy_value_table(backend: DatabaseBackend) -> Iterator[str]:
    """Build, swap in the pre-ecp_code table, and restore it afterwards.

    The restore matters on SQL Server, where every test shares one database.
    Yields the NAACCR DDL path the upgrade forces.
    """

    BuildRunner(load_manifest(), backend).run()
    ddl_path = BuildRunner._NAACCR_VALUE_DDL[backend.dialect]
    backend.execute("DROP TABLE naaccr.naaccr_value")
    backend.execute(_LEGACY_VALUE_DDL[backend.dialect])
    try:
        yield ddl_path
    finally:
        if backend.table_exists("naaccr", "naaccr_value"):
            backend.execute("DROP TABLE naaccr.naaccr_value")
        sql = repository_path(ddl_path).read_text(encoding="utf-8")
        backend.execute_units(split_script(backend.dialect, sql).executable)


def _status_of(actions: list[BuildAction], path: str) -> BuildStatus:
    return next(action.status for action in actions if action.path == path)


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_empty_legacy_value_table_upgrades_even_when_hashes_are_accepted(
    dialect: str, tmp_path: Path
) -> None:
    with _backend(dialect, tmp_path) as backend, _legacy_value_table(
        backend
    ) as ddl_path:
        preview = BuildRunner(load_manifest(), backend).run(dry_run=True)
        assert _status_of(preview, ddl_path) is BuildStatus.WOULD_REAPPLY
        runner = BuildRunner(load_manifest(), backend, accept_changed_hashes=True)
        actions = runner.run()
        assert _status_of(actions, ddl_path) is BuildStatus.REAPPLIED
        assert runner._naaccr_value_shape() == (True, True)
        assert backend.fetch_one("SELECT COUNT(*) FROM naaccr.naaccr_value")[0] == 0


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_empty_legacy_value_table_without_a_ledger_row_is_applied(
    dialect: str, tmp_path: Path
) -> None:
    with _backend(dialect, tmp_path) as backend, _legacy_value_table(
        backend
    ) as ddl_path:
        backend.execute(
            "DELETE FROM etl.schema_migration WHERE migration_path = ?", (ddl_path,)
        )
        preview = BuildRunner(load_manifest(), backend).run(dry_run=True)
        assert _status_of(preview, ddl_path) is BuildStatus.WOULD_APPLY
        runner = BuildRunner(load_manifest(), backend)
        actions = runner.run()
        assert _status_of(actions, ddl_path) is BuildStatus.APPLIED
        assert runner._naaccr_value_shape() == (True, True)


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_populated_legacy_value_table_fails_without_changing_rows(
    dialect: str, tmp_path: Path
) -> None:
    with _backend(dialect, tmp_path) as backend, _legacy_value_table(backend):
        backend.execute(_INSERT_LEGACY_ROW)
        run_count = backend.fetch_one("SELECT COUNT(*) FROM etl.run")[0]
        with pytest.raises(RuntimeError, match="1 legacy row.*ambiguous"):
            BuildRunner(load_manifest(), backend).run(dry_run=True)
        with pytest.raises(RuntimeError, match="1 legacy row.*ambiguous"):
            BuildRunner(load_manifest(), backend).run()
        assert tuple(
            backend.fetch_one(
                "SELECT person_id, episode_key, item_num FROM naaccr.naaccr_value"
            )
        ) == (1, "legacy", 2118)
        assert backend.fetch_one("SELECT COUNT(*) FROM etl.run")[0] == run_count


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_row_added_after_the_early_check_blocks_the_drop(
    dialect: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _backend(dialect, tmp_path) as backend, _legacy_value_table(backend):
        prepare_for_writes = backend.prepare_for_writes

        def prepare_then_race() -> None:
            # An importer lands between the early count and the drop.
            prepare_for_writes()
            backend.execute(_INSERT_LEGACY_ROW)

        monkeypatch.setattr(backend, "prepare_for_writes", prepare_then_race)
        with pytest.raises(RuntimeError, match="1 legacy row.*ambiguous"):
            BuildRunner(load_manifest(), backend).run()
        assert tuple(
            backend.fetch_one(
                "SELECT person_id, episode_key, item_num FROM naaccr.naaccr_value"
            )
        ) == (1, "legacy", 2118)


def test_dry_run_against_a_new_database_writes_nothing_to_disk(tmp_path: Path) -> None:
    control_path = tmp_path / "unbuilt" / "demo.db"

    assert main(["build", "--dialect", "sqlite", "--db", str(control_path), "--dry-run"]) == 0

    assert not control_path.parent.exists()


def test_dry_run_does_not_mutate_the_ledger(tmp_path: Path) -> None:
    control_path = tmp_path / "build.db"
    _run_build(control_path)
    with SQLiteBackend(control_path) as backend:
        before = backend.fetch_one("SELECT COUNT(*) FROM etl.run")[0]
    actions = _run_build(control_path, dry_run=True)
    with SQLiteBackend(control_path) as backend:
        after = backend.fetch_one("SELECT COUNT(*) FROM etl.run")[0]

    assert before == after
    assert all(action.status is BuildStatus.SKIPPED for action in actions)


def test_dry_run_over_an_existing_build_leaves_every_file_byte_identical(
    tmp_path: Path,
) -> None:
    control_path = tmp_path / "demo.db"
    _run_build(control_path)

    def digests() -> dict[str, str]:
        return {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(tmp_path.iterdir())
        }

    before = digests()
    # Goes through the CLI so the read-only backend is what reads the ledger.
    assert main(["build", "--dialect", "sqlite", "--db", str(control_path), "--dry-run"]) == 0

    assert digests() == before


def test_second_build_without_the_ledger_fails(tmp_path: Path) -> None:
    control_path = tmp_path / "build.db"
    _run_build(control_path)
    with SQLiteBackend(control_path) as backend:
        backend.execute("DROP TABLE etl.schema_migration")

    with pytest.raises(sqlite3.OperationalError, match="already exists"):
        _run_build(control_path)


def test_naaccr_person_id_accepts_intake_patient_without_omop_person(tmp_path: Path) -> None:
    control_path = tmp_path / "build.db"
    _run_build(control_path)
    with SQLiteBackend(control_path) as backend:
        patient_id = backend.execute(
            "INSERT INTO intake.patient (person_source_value, assigning_authority) VALUES (?, ?)",
            ("patient-1", "authority-a"),
        )
        backend.execute(
            "INSERT INTO naaccr.naaccr_value (person_id, episode_key, item_num) VALUES (?, ?, ?)",
            (patient_id, "episode-1", 100),
        )
        assert backend.fetch_one("SELECT COUNT(*) FROM omop.person")[0] == 0
        assert backend.fetch_one("SELECT person_id FROM naaccr.naaccr_value")[0] == patient_id


def test_sqlite_schema_files_follow_the_control_database_name(tmp_path: Path) -> None:
    control_path = tmp_path / "demo.db"
    _run_build(control_path)

    for schema in ("etl", "intake", "omop", "naaccr", "sdc"):
        assert schema_database_path(control_path, schema).is_file()
