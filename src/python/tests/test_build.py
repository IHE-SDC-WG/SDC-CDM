from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sdc_cdm.cli.build import BuildRunner, BuildStatus
from sdc_cdm.cli.main import main, registered_commands
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.sqlite_backend import SQLiteBackend, schema_database_path


def _run_build(control_path: Path, *, dry_run: bool = False):
    with SQLiteBackend(control_path) as backend:
        return BuildRunner(load_manifest(), backend).run(dry_run=dry_run)


def test_only_build_command_is_registered() -> None:
    assert registered_commands() == ("build",)
    with pytest.raises(SystemExit) as exc_info:
        main(["ingest"])
    assert exc_info.value.code == 2


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
        assert backend.table_exists("omop", "measurement")
        assert backend.table_exists("naaccr", "naaccr_value")
        assert backend.table_exists("sdc", "sdc_report")


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
